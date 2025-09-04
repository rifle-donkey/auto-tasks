# ipam_client/utils.py
from datetime import datetime
from socket import inet_ntoa
from struct import pack
from math import log2
import logging
import zipfile
import time
import csv
import os


def set_timestamp():
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")


def exec_timestamp():
    return time.time()


# This function set timestamps for IPAM
def ipm_timestamp():
    now = datetime.now()
    return now.strftime("%B %d, %Y, %-I:%M %p")


def size_to_prefix(f_size):
    try:
        if 0 < int(f_size) <= 16777216:
            return int(32 - log2(int(f_size)))
        else:
            logging.error(f"Size error, verify input: {f_size}")
            return 0
    except ValueError:
        logging.error(f"Size error, verify input: {f_size}")
        return 0


def hex_to_ip(f_hex_addr):
    f_addr_long = int(f_hex_addr, 16)
    return inet_ntoa(pack(">L", f_addr_long))


# Function write to csv
def write_list_to_csv(f_content_source, f_target_file):
    with open(f_target_file, 'w+', encoding='UTF-8' ,newline='') as f_fileobject:
        f_writer = csv.DictWriter(f_fileobject, delimiter=',', fieldnames=f_content_source[0].keys())
        f_writer.writeheader()
        f_writer.writerows(f_content_source)
        f_fileobject.close()


# Function logging
def write_to_splunk(f_content_source, f_log_splunk):
    with open(f_log_splunk, 'w+', encoding='UTF-8', newline='') as f_fsplunk_object:
        for f_content in f_content_source:
            f_fbody = " ".join("{}=\"{}\"".format(*f_i) for f_i in f_content.items())
            f_fsplunk_object.write("%s\n" % f_fbody)
        f_fsplunk_object.close()


# Function archive existing file
def archive_file(f_target_file, f_archive_file):
    if os.path.isfile(f_target_file):
        bakup = zipfile.ZipFile(f_archive_file, 'w')
        bakup.write(f_target_file, compress_type=zipfile.ZIP_DEFLATED)
        bakup.close()
        os.chmod(f_archive_file, 0o644)