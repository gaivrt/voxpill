"""Package webrtcvad-wheels without the stale upstream distribution-name hook."""

from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata("webrtcvad-wheels")
