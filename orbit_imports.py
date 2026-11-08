"""Identify launch candidates from the exact files of a completed download."""
import os
from pathlib import Path
import re

HELPERS=re.compile(r'(?:^|[/_ .-])(?:setup\d*|install(?:er)?|unins\w*|uninstall\w*|vcredist\w*|vc_redist\w*|dxsetup|redist|crash\w*|unitycrashhandler\w*|ue[45]prereq\w*|reporter|cefsubprocess|steamerrorreporter)(?:$|[/_ .-])',re.I)


def detect_download(download, windows=False):
    root=Path(download['path']).resolve()
    candidates=[]
    for name in download.get('files',[]):
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            continue
        path=root/relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            continue
        if HELPERS.search(relative.with_suffix('').as_posix()):
            continue
        suffix=path.suffix.lower()
        if suffix in ('.exe','.com') or (not windows and (suffix in ('.appimage','.sh') or (not suffix and os.access(path,os.X_OK)))):
            candidates.append(path)
    # Native builds take precedence on Linux; prefer 64-bit variants on both OSes.
    if not windows and any(p.suffix.lower() not in ('.exe','.com') for p in candidates):
        candidates=[p for p in candidates if p.suffix.lower() not in ('.exe','.com')]
    x64=[p for p in candidates if re.search(r'(?:win64|x64|x86_64|amd64|64bit)',str(p),re.I)]
    if x64:
        candidates=x64
    chosen=candidates[0] if len(candidates)==1 else None
    return {'path':str(chosen) if chosen else '', 'candidates':[str(p) for p in candidates], 'needsSetup':chosen is None or (not windows and chosen.suffix.lower() not in ('.exe','.com') and not os.access(chosen,os.X_OK))}
