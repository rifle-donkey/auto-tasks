### Script description ###
# This script read terminal networks of distribute sites, generate csv report to ipinfohub and log to Splunk.
#
### End of Description ###

##################
# Version Control
#
#  v2.1, change to use class to manage IPAM API call    
#
##################
# Change logs
# v1.0, initial version
# v1.1, first release
# v1.2, add terminal subnet used in central environment.
# v1.3, merge distribute and NOC terminal subnets into one output
# v1.4, add DNS domain
# v1.5, add output to GitHUB.
# v1.6, adding segment type to output
# v1.7, adding solution and vlan_range, vlan_domain to output
# v1.8, adding static IP utilization
# v2.0, change to use class to manage IPAM API call
# v2.1, change to use class to manage IPAM API call
### Load Python module ###
import requests
import urllib3
import base64
import os
import sys
import csv
import git
import json
import zipfile
import logging
from tqdm import tqdm
from math import log2
from datetime import datetime
### End of module load ###


### Function declaration ###
def setup_logging():
    log_file = "/var/automation_log/network_inventory/list_terminal_network.log"
    # Configure logging
    datefmt = '%Y-%m-%d %H:%M:%S'
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt=datefmt
    )
    return log_file


# This function is to get credential from configuration file and decrypt it
# The function requires one input to identify which credential to read and decrypt
# Valid option of "Section" are "IPAM" and "HPE_OOB"
def get_credential(f_section):
    import configparser
    from cryptography.fernet import Fernet
    f_home_env = os.getenv("HOME")
    f_config = configparser.ConfigParser()
    f_conf_file = f"{f_home_env}/.config/credential.ini"
    try:
        # Read crypto key from configuration file
        f_config.read(f_conf_file)
        f_crypto_key = f_config["KEY"]["crypto_key"]
        # Read and decrypt credential from configuration file
        f_crypto = Fernet(f_crypto_key)
        f_decrypted_usr = f_crypto.decrypt(f_config[f_section]["hash_usr"].encode()).decode("UTF-8")
        f_decrypted_pwd = f_crypto.decrypt(f_config[f_section]["hash_pwd"].encode()).decode("UTF-8")
        # Base64 encode username and password
        f_encode_usr = base64.b64encode(f_decrypted_usr.encode()).decode("UTF-8")
        f_encode_pwd = base64.b64encode(f_decrypted_pwd.encode()).decode("UTF-8")
    except Exception as f_error:
        logging.error(f"Retrieve credential failed. Error: {f_error}")
        sys.exit(1)
    #
    return f_encode_usr, f_encode_pwd


# This fucnetion push GitHUB to upload eox file
def push_git(f_dir, f_file_list):
    f_repo = git.Repo(f_dir)
    f_commit_msg = "Update terminal networks."
    f_repo.index.add(f_file_list)
    f_repo.index.commit(f_commit_msg)
    f_orign = f_repo.remote('origin')
    f_orign.push()


class IPAMClient:
    def __init__(self, base_url, usr, pwd):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "X-IPM-Username": usr,
            "X-IPM-Password": pwd,
            "cache-control": "no-cache"
        })
        requests.packages.urllib3.disable_warnings()
        self.logger = logging.getLogger(__name__)

    def _request(self, method, api_call, input_param, rpc=False):
        query_url = f"{self.base_url}/{'rpc' if rpc else 'rest'}/{api_call}"
        try:
            response = getattr(self.session, method)(
                query_url,
                params=input_param,
                verify=False
            )
            response.raise_for_status()
            response_code = response.status_code
            query_response = response.json() if response_code in [200, 201, 400] else response.text
        except requests.exceptions.HTTPError as http_err:
            self.logger.error(f"HTTP error occurred: Code: {http_err.response.status_code}")
            return http_err.response.status_code, f"HTTP error occurred: {http_err}"
        except requests.exceptions.RequestException as req_err:
            self.logger.error(f"Request error occurred: Code: {req_err.response.status_code}")
            return req_err.response.status_code, f"Request error occurred: {req_err}"
        except Exception as err:
            self.logger.error(f"An error occurred: {err}")
            return "500", f"An error occurred: {err}"
        # Return response code and response data
        return response_code, query_response
    
    def get(self, api_call, input_param):
        return self._request("get", api_call, input_param)

    def post(self, api_call, input_param):
        return self._request("post", api_call, input_param)

    def put(self, api_call, input_param):
        return self._request("put", api_call, input_param)
    
    def delete(self, api_call, input_param):
        return self._request("delete", api_call, input_param)
    
    def rpc(self, api_call, input_param):
        return self._request("options", api_call, input_param, rpc=True)
    

# Function log to splunk
def write_to_splunk(f_content_list, f_log_file):
    with open(f_log_file, 'a') as f_fsplunk_object:
        for f_content in f_content_list:
            f_content["Script"] = "list_terminal_network.py"
            f_fbody = " ".join("{}=\"{}\"".format(*f_i) for f_i in f_content.items())
            f_fsplunk_object.write("%s\n" % f_fbody)
        f_fsplunk_object.close()


# Function write to csv
def write_list_to_csv(f_content_source, f_target_file):
    with open(f_target_file, 'w+', encoding='UTF-8' ,newline='') as f_fileobject:
        f_writer = csv.DictWriter(f_fileobject, delimiter=',', fieldnames=f_content_source[0].keys())
        f_writer.writeheader()
        f_writer.writerows(f_content_source)
        f_fileobject.close()
    os.chmod(f_target_file, 0o644)


# This function set timestamps
def set_timestamp():
    now = datetime.now()
    f_timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    return f_timestamp


# This function set execute timestamp
def exec_timestamp():
    from datetime import datetime
    f_now = datetime.now()
    f_timestamp = f_now.strftime("%Y-%m-%d %H:%M:%S")
    return f_timestamp


# Function to convert prefix to subnet size
def size_to_prefix(f_size):
    try:
        if int(f_size) > 0 and int(f_size) <= 16777216:
            f_prefix = 32 - int(log2(int(f_size)))
            logging.info("converted")
        else:
            f_prefix = 0
            logging.error("Size error, verify input")
    except ValueError:
        f_prefix = 0
        logging.error("Size error, verify input")

    return int(f_prefix)


# This function convert hex format address to dot decimal format
def hex_to_ip(f_hex_addr):
    """convert HEX format IP address to dotted decimal"""
    from socket import inet_ntoa
    from struct import pack
    f_addr_long = int(f_hex_addr, 16)
    f_dotted_address = inet_ntoa(pack(">L", f_addr_long))
    return f_dotted_address


# This function retrieve number of used static IP addresses from IPAM
def count_used_ip(f_ipamclient, f_id):
    f_counter = {"WHERE": f"subnet_id='{f_id}'"}
    f_counter_result = f_ipamclient.get("ip_used_address_count", f_counter)
    #
    if f_counter_result[0] != 200:
        logging.error(f"Internal failure, error message: {f_counter_result}. Please contact IPAM Admin.")
        return None
    else:
        f_usedip = f_counter_result[1][0]['total']
        return int(f_usedip)


# This function retrieve number of used DHCP leases from IPAM
def count_used_dhcp_leases(f_ipamclient, f_id):
    f_counter = {"WHERE": f"pool_id='{f_id}'"}
    f_counter_result = f_ipamclient.get("ip_used_address_count", f_counter)
    #
    if f_counter_result[0] != 200:
        logging.error(f"Internal failure, error message: {f_counter_result}. Please contact IPAM Admin.")
        return None
    else:
        f_usedip = f_counter_result[1][0]['total']
        return int(f_usedip)
    

# This function retrieve DHCP ranges
def read_dhcp_range(f_ipamclient):
    f_dhcp_pool = {}
    logging.info("Reading DHCP pool from IPAM......")
    f_select = "pool_id,pool_name,pool_size,subnet_id"
    f_dhcp = {"SELECT": f_select,
              "WHERE": "site_id='2' and pool_name LIKE 'DHCP%'",
              "GROUPBY": ""
             }
    f_dhcp_result = f_ipamclient.get("ip_pool_groupby", f_dhcp)
    #
    if f_dhcp_result[0] != 200:
        logging.error(f"Could not read out DHCP pool, error message: {f_dhcp_result}. Please contact IPAM Admin.")
        return {}
    else:
        logging.info(f"Found {len(f_dhcp_result[1])} DHCP pools")
        logging.info("------ Count used IP from DHCP pool -----")
        f_pbar = tqdm(total=len(f_dhcp_result[1]))
        for f_pool in f_dhcp_result[1]:
            f_poolid = f_pool['pool_id']
            f_poolsize = f_pool['pool_size']
            f_netid = f_pool['subnet_id']
            f_used_lease = count_used_dhcp_leases(f_ipamclient, f_poolid) 
            #
            if f_used_lease:
                if f_netid not in f_dhcp_pool.keys():
                    f_dhcp_pool[f_netid] = {
                        "DHCP_Size": int(f_poolsize),
                        "Used_Lease": f_used_lease,
                    }
                else:
                    f_dhcp_pool[f_netid]["Used_Lease"] += f_used_lease
                    f_dhcp_pool[f_netid]["DHCP_Size"] += int(f_poolsize)

            else:
                if f_netid not in f_dhcp_pool.keys():
                    f_dhcp_pool[f_netid] = {
                        "DHCP_Size": int(f_poolsize),
                        "Used_Lease": 0,
                    }
                else:
                    f_dhcp_pool[f_netid]["Used_Lease"] += 0
                    f_dhcp_pool[f_netid]["DHCP_Size"] += int(f_poolsize)
            #
            f_pbar.update(1)
        f_pbar.close()
        logging.info("Read DHCP pool completed.")
        return f_dhcp_pool


# This function retrieve terminal networks marked by distribute
def read_network_terminal(f_ipamclient, f_dhcp_pool=[]):
    f_network_terminal = []
    logging.info("Reading terminal network from IPAM......")
    f_tags = ['ikea_network_subnet_mgnt',
              'ikea_network_subnet_tenant',
              'ikea_pvlan_tag',
              'ikea_pvlan_isolate_id',
              'ikea_region',
              'ikea_country',
              'ikea_country_code',
              'ikea_country_code_iso_2',
              'ikea_city_name',
              'ikea_city_name_abbrev',
              'ikea_site_name',
              'ikea_site_name_abbrev',
              'ikea_site_type',
              'ikea_site_sub_type',
              'ikea_channel_id',
              'domain',
             ]
    f_tag_str = "&".join("network.{}".format(f_i) for f_i in f_tags)
    f_select_tags = ",".join("tag_network_{}".format(f_i) for f_i in f_tags)
    f_select = "subnet_id,start_hostaddr,subnet_name,subnet_size,subnet_ip_used_size,subnet_class_name,vlmvlan_vlan_id,vlmvlan_name,vlmdomain_name,parent_subnet_name,parent_start_ip_addr,parent_subnet_size,parent_subnet_class_name,{}".format(f_select_tags)
    f_read_net = {"TAGS": f_tag_str,
                  "SELECT": f_select,
                  "WHERE": "site_id='2' and is_terminal='1'",
                  "GROUPBY": "",
                  "ORDERBY": "start_hostaddr"
                 }
    f_read_net_result = f_ipamclient.get("ip_block_subnet_groupby", f_read_net)
    #
    if f_read_net_result[0] != 200:
        logging.error(f"Could not read out network, error message: {f_read_net_result}. Please contact IPAM Admin.")
        return []
    else:
        logging.info("------ Read terminal network complete, sort and generate report -----")
        f_pbar = tqdm(total=len(f_read_net_result[1]))
        for f_net in f_read_net_result[1]:
            f_net_name = f_net['subnet_name']
            f_vlan_id = int(f_net['vlmvlan_vlan_id'])
            if f_vlan_id == 0 and f_net_name == "Default":
                logging.info("Skip Orphan Address Container")
                continue
            #
            f_netid = f_net['subnet_id']
            f_startaddr = f_net['start_hostaddr']
            f_netsize = f"{int(f_net['subnet_size']) - 2}" if int(f_net['subnet_size']) >= 4 else int(f_net['subnet_size'])
            f_netaddr = f"{f_startaddr}/{size_to_prefix(f_netsize)}"
            f_used_ip = f_net['subnet_ip_used_size']
            f_network = {
                "Name": f_net_name,
                "NET_Addr": f_netaddr,
                "NET_Size": f_netsize,
                "NET_Utilization": f"{round((float(f_used_ip) / float(f_netsize)) * 100, 2)}%",
                "VLAN_ID": f_vlan_id,
                "VLAN_Name": f_net['vlmvlan_name'],
                "VLAN_Domain": f_net['vlmdomain_name'],
                "Private_VLAN": f_net['tag_network_ikea_pvlan_tag'],
                "Private_VLAN_ID": f_net['tag_network_ikea_pvlan_isolate_id'] if f_net['tag_network_ikea_pvlan_isolate_id'] else "N/A",
                "Mgmt_Network": f_net['tag_network_ikea_network_subnet_mgnt'],
                "Tenant": f_net['tag_network_ikea_network_subnet_tenant'],
                "Subnet_Class": f_net['subnet_class_name'],
                "Parent_Name": f_net['parent_subnet_name'],
                "Parent_Class": f_net['parent_subnet_class_name'],
                "Parent_Addr": "{}/{}".format(hex_to_ip(f_net['parent_start_ip_addr']), size_to_prefix(f_net['parent_subnet_size'])),
                "Region": f_net['tag_network_ikea_region'],
                "Country": f_net['tag_network_ikea_country'],
                "Country_code": f_net['tag_network_ikea_country_code'],
                "Country_code_iso_2": f_net['tag_network_ikea_country_code_iso_2'],
                "City": f_net['tag_network_ikea_city_name'],
                "City_abbrev": f_net['tag_network_ikea_city_name_abbrev'],
                "Site": f_net['tag_network_ikea_site_name'],
                "Site_abbrev": f_net['tag_network_ikea_site_name_abbrev'],
                "Site_Type": f_net['tag_network_ikea_site_sub_type'],
                "Site_Type_CBD": f_net['tag_network_ikea_site_type'],
                "Channel_ID": f_net['tag_network_ikea_channel_id'],
                "DNS_Domain": f_net['tag_network_domain'],
            }
            # Attache DHCP info
            if f_dhcp_pool:
                if f_netid in f_dhcp_pool.keys():
                    f_dhcpinfo = f_dhcp_pool[f_netid]
                    f_dhcpsize = f_dhcpinfo['DHCP_Size']
                    f_used_lease = f_dhcpinfo['Used_Lease']
                    f_pool_util = "{}%".format(round((float(f_used_lease) / float(f_dhcpsize)) * 100, 2))
                    try:
                        f_staticip_util = f"{round(((float(f_used_ip) - float(f_used_lease)) / (float(f_netsize) - float(f_dhcpsize))) * 100, 2)}%"
                    except ZeroDivisionError:
                        f_staticip_util = "NA"
                        logging.warning(f"{f_netaddr} does not have space for static IP, DHCP takes all valid IPs.")
                        
                    f_network["DHCP_Size"] = f_dhcpsize
                    f_network["DHCP_Utilization"] = f_pool_util
                    f_network["Static_IP_Utilization"] = f_staticip_util
                else:
                    f_staticip_util = f"{round((float(f_used_ip) / float(f_netsize)) * 100, 2)}%"
                    f_network["DHCP_Size"] = "0"
                    f_network["DHCP_Utilization"] = "NA"
                    f_network["Static_IP_Utilization"] = f_staticip_util

            # save to output
            f_network_terminal.append(f_network)
            f_pbar.update(1)
        f_pbar.close()
        logging.info("Read terminal network completed.")
        return f_network_terminal

### End of Function declaration ###


### Main body start ###
# Initiate logging
log_file = setup_logging()
open(log_file, 'w', encoding='UTF-8').close()
os.chmod(log_file, 0o644)
# Set start timestamp
timestamps = set_timestamp()
start_timestamp = exec_timestamp()
print("Script start at {}".format(start_timestamp))
# Declare global variables, file path, logging path, files etc.
inventory_path = "/var/automation_file/Network_Inventory"
splunk_report = "/var/automation_log/splunk_log/network_inventory.log"
#
inventory_file = f"{inventory_path}/network_inventory.csv"
#
# Git
home_path = os.getenv("HOME")
repo_path = "{}/GitHub/IPAM_Data/segment_inventory".format(home_path)
git_file_list = []
repo_dir = "IPAM_Data"
if not os.path.exists(repo_path):
    os.makedirs(repo_path)
    os.chmod(repo_path, 0o755)
# Set IPAM credential
usr, pwd = get_credential("IPAM")
# Initiate IPAM client
ipamclient = IPAMClient("https://ipam.ikea.com", usr, pwd)  
# Read DHCP range from IPAM
dhcp_pool = read_dhcp_range(ipamclient)
# Read network from IPAM
if not dhcp_pool:
    logging.error("No DHCP pool found, please check IPAM.")
    terminal_networks = []
else:
    terminal_networks = read_network_terminal(ipamclient, dhcp_pool)
# Generate terminal network output
if not terminal_networks:
    logging.error("No terminal network found, please check IPAM.")
else:
    # Create csv version terminal networks
    write_list_to_csv(terminal_networks, inventory_file)
    # Create splunk report
    open(splunk_report, 'w', encoding='UTF-8').close()
    os.chmod(splunk_report, 0o644)
    write_to_splunk(terminal_networks, splunk_report)
    # Create GitHUB version terminal networks
    network_repo = f"{repo_path}/terminal_networks.csv"
    git_file_list.append("segment_inventory/terminal_networks.csv")
    write_list_to_csv(terminal_networks, network_repo)
    # Push update into GitHUB
    if git_file_list:
        logging.info("Push new terminal networks to GitHUB")
        os.chdir("{}/GitHub".format(home_path))
        push_git(repo_dir, git_file_list)
# Print EoP
end_timestamp = exec_timestamp()
logging.info("List networks completed at {}".format(end_timestamp))
print("List networks completed at {}".format(end_timestamp))
