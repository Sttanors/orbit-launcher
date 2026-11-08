import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orbit_evening import recommend, validate_profile
from launcher import Library


class EveningTests(unittest.TestCase):
    def setUp(self):
        self.games = [{'id': str(i), 'name': 'Game '+str(i), 'installed': True, 'lastPlayed': i*1000} for i in range(6)]
        self.profiles = {str(i): {'minutes': 20 if i<3 else 60, 'moods': ['relax', 'friends']} for i in range(6)}

    def test_time_mood_and_ready_state_are_strict(self):
        self.games[0]['installed'] = False
        self.games[1]['needsSetup'] = True
        self.assertEqual([p['game']['id'] for p in recommend(self.games,self.profiles,20,'friends')['picks']],['2'])
        self.assertEqual(recommend(self.games,self.profiles,240,'think')['picks'],[])
        self.assertEqual(recommend(self.games,{},240,'relax')['picks'],[])

    def test_three_unique_games_and_long_sessions(self):
        picks=recommend(self.games,self.profiles,60,'relax')['picks']
        self.assertEqual(len(picks),3)
        self.assertEqual(len({p['game']['id'] for p in picks}),3)
        self.profiles['0']['minutes']=240
        self.assertNotIn('0',[p['game']['id'] for p in recommend(self.games,self.profiles,60,'relax')['picks']])
        self.assertIn('0',[p['game']['id'] for p in recommend(self.games,self.profiles,240,'relax')['picks']])

    def test_surprise_works_without_tags_and_prefers_old_history(self):
        picks=recommend(self.games,{},surprise=True)['picks']
        self.assertEqual([p['game']['id'] for p in picks],['0'])
        self.assertEqual(recommend([],{},surprise=True)['picks'],[])

    def test_redraw_avoids_last_draw_and_fills_small_libraries(self):
        first=recommend(self.games,self.profiles)['picks']
        ids=[p['game']['id'] for p in first]
        second=recommend(self.games,self.profiles,exclude=ids)['picks']
        self.assertTrue(set(ids).isdisjoint(p['game']['id'] for p in second))
        self.assertEqual(len(recommend(self.games[:2],self.profiles,exclude=['0','1'])['picks']),2)
        self.assertEqual(recommend(self.games,{},surprise=True,exclude=['0'])['picks'][0]['game']['id'],'1')

    def test_random_ties_do_not_mutate_library(self):
        for game in self.games:game['lastPlayed']=0
        before=list(self.games)
        a=recommend(self.games,self.profiles,rng=random.Random(1))['picks']
        b=recommend(self.games,self.profiles,rng=random.Random(2))['picks']
        self.assertNotEqual([p['game']['id'] for p in a],[p['game']['id'] for p in b])
        self.assertEqual(self.games,before)

    def test_invalid_profiles_and_requests(self):
        for minutes,moods in [(True,['relax']),(15,['relax']),(20,[]),(20,['unknown']),(20,'relax'),(20,[{}])]:
            with self.assertRaises(ValueError):validate_profile(minutes,moods)
        self.assertEqual(validate_profile(20,['relax','relax'])['moods'],['relax'])
        with self.assertRaises(ValueError):recommend(self.games,self.profiles,mood=[])

    def test_profiles_survive_restart_and_old_libraries_migrate(self):
        with tempfile.TemporaryDirectory() as temp, patch('launcher.scan_steam',return_value=[]):
            library=Library(temp);self.assertEqual(library.state['eveningProfiles'],{})
            library.state['eveningProfiles']['steam-1']=validate_profile(60,['think'])
            library.save()
            self.assertEqual(Library(temp).state['eveningProfiles'],library.state['eveningProfiles'])


if __name__=='__main__':unittest.main()
