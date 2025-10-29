from __future__ import annotations
from fastapi import FastAPI
from vfoundation.obs.debug_api import app as _app

app: FastAPI = _app  # expose debug app as main
