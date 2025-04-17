"""
    Modulo principal de clases, funciones y metodos
"""

import os
import sys
import json
import logging
import logging.config
from datetime import datetime
import time
import random
import string
import configparser
import shutil
import warnings
import sqlite3
import subprocess
warnings.simplefilter("ignore")

import yaml
from urllib.parse import quote
import win32com.client as win32
from tabulate import tabulate
from fpdf import FPDF
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image, ImageTk
from sqlalchemy import create_engine, engine, text
