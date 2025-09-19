# ipam_sdk/utils/file.py
"""File operation utilities for IPAM data export and archiving."""

import csv
import zipfile
import os


def write_list_to_csv(f_content_source, f_target_file):
    """
    Write list of dictionaries to CSV file.
    
    Args:
        f_content_source (list): List of dictionaries with data
        f_target_file (str): Target CSV file path
    """
    with open(f_target_file, 'w+', encoding='UTF-8', newline='') as f_fileobject:
        f_writer = csv.DictWriter(f_fileobject, delimiter=',', fieldnames=f_content_source[0].keys())
        f_writer.writeheader()
        f_writer.writerows(f_content_source)
        f_fileobject.close()


def write_to_splunk(f_content_source, f_log_splunk):
    """
    Write data to Splunk-compatible log format.
    
    Args:
        f_content_source (list): List of dictionaries with data
        f_log_splunk (str): Target Splunk log file path
    """
    with open(f_log_splunk, 'w+', encoding='UTF-8', newline='') as f_fsplunk_object:
        for f_content in f_content_source:
            f_fbody = " ".join("{}=\"{}\"".format(*f_i) for f_i in f_content.items())
            f_fsplunk_object.write("%s\n" % f_fbody)
        f_fsplunk_object.close()


def archive_file(f_target_file, f_archive_file):
    """
    Archive an existing file to a ZIP archive.
    
    Args:
        f_target_file (str): File to be archived
        f_archive_file (str): Target archive file path
    """
    if os.path.isfile(f_target_file):
        bakup = zipfile.ZipFile(f_archive_file, 'w')
        bakup.write(f_target_file, compress_type=zipfile.ZIP_DEFLATED)
        bakup.close()
        os.chmod(f_archive_file, 0o644)