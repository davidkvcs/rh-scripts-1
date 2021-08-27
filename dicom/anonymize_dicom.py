#!/usr/bin/env python
from __future__ import print_function
import argparse
import os, sys, glob
import pydicom as dicom
import datetime
from rhscripts.dcm import Anonymize, generate_SeriesInstanceUID

__scriptname__ = 'anonymize_dicom'
__version__ = '0.0.2'

"""
VERSIONING
  0.0.1 # Created script
  0.0.2 # Removed option to give SeriesInstanceUID, this is autogenerated when
          the replaceUIDs flag is set
"""

"""

Date: 1/6-2018
Author: Claes Ladefoged ( claes.noehr.ladefoged@regionh.dk )

###

Anonymize script for DICOM file or folder containing dicom files
Simply removes or replaces patient sensitive information.

-----------------------------------------------------------------

### USAGE
usage: anonymize_dicom.py [-h] [--name NAME] original output

Convert DICOM to MINC

positional arguments:
  original     Folder or file of original dicom files
  output       Folder or file of anonymized dicom files

optional arguments:
  -h, --help   show this help message and exit
  --name NAME  Name instead of patient name
  --replaceUIDs
  --StudyInstanceUID

-----------------------------------------------------------------

"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Convert DICOM to MINC')

    parser.add_argument('original', type=str, help='Folder or file of original dicom files')
    parser.add_argument('output', type=str, help='Folder or file of anonymized dicom files')
    parser.add_argument('--name', help='Name instead of patient name')
    parser.add_argument('--replace_uids', help="Replace the UIDs", action="store_true")
    parser.add_argument('--StudyInstanceUID', help='Set the UID. Otherwise auto generated')
    args = parser.parse_args()

    anon = Anonymize()

    if os.path.isdir(args.original):
        anon.anonymize_folder(args.original,args.output,args.name,
                         studyInstanceUID=args.StudyInstanceUID,
                         replaceUIDs=args.replace_uids)
    else:
        # Generate a new series instance if only a single file is being
        # anonymized (e.g. a RTSS struct)
        seriesInstanceUID = None if not args.replace_uids \
                            else generate_SeriesInstanceUID()
        anon.anonymize_file(args.original,args.output,args.name,
                  studyInstanceUID=args.StudyInstanceUID,
                  seriesInstanceUID=seriesInstanceUID,
                  replaceUIDs=args.replace_uids)
