### Script description ###
# This script read DHCP usage for vlan101 from IPAM and generate report send to splunk
### End of Description ###

##################
# Version Control
#
#  v1.0
#
##################
# Change logs
# v1.0, initial version

### Load Python module ###
import requests
import base64
import os
import sys
import csv
import logging
from math import log2
from datetime import datetime
### End of module load ###


### Function declaration ###
def setup_logging():
    log_file = "/var/automation_log/network_inventory/vlan101_dhcp_usage.log"
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


# This function set timestamps
def set_timestamp():
    now = datetime.now()
    f_timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    return f_timestamp


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
            f_content["Script"] = "dhcp_usage_vlan101.py"
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


# This function retrieve number of used DHCP leases from IPAM
def count_used_dhcp_leases(f_ipamclient, pool_id):
    f_counter = {"WHERE": f"pool_id='{pool_id}'"}
    f_counter_result = f_ipamclient.get("ip_used_address_count", f_counter)
    #
    if f_counter_result[0] != 200:
        logging.error(f"Internal failure, error message: {f_counter_result}. Please contact IPAM Admin.")
        return None
    else:
        f_usedip = f_counter_result[1][0]['total']
        return int(f_usedip)
    

# This function retrieve DHCP ranges
def read_dhcp_range(f_ipamclient, f_netid=None):
    f_dhcp_pool = {"DHCP_Size": 0, "Used_Lease": 0, "DHCP_Usage": "0%"}
    logging.info("Reading DHCP pool from IPAM......")
    f_select = "pool_id,pool_size"
    f_dhcp = {"SELECT": f_select,
              "WHERE": f"site_id='2' and subnet_id='{f_netid}'",
              "GROUPBY": ""
             }
    f_code, f_dhcp_result = f_ipamclient.get("ip_pool_groupby", f_dhcp)
    #
    if f_code != 200:
        logging.error(f"Could not read out DHCP pool, error message: {f_dhcp_result}. Please contact IPAM Admin.")
        return f_dhcp_pool
    else:
        logging.info("------ Count used IP from DHCP pool -----")
        for f_pool in f_dhcp_result:
            f_poolid = f_pool['pool_id']
            f_poolsize = f_pool['pool_size']
            f_used_lease = count_used_dhcp_leases(f_ipamclient, f_poolid) 
            #
            if f_used_lease:
                f_dhcp_pool["Used_Lease"] += int(f_used_lease)
                f_dhcp_pool["DHCP_Size"] += int(f_poolsize)
            else:
                f_dhcp_pool["Used_Lease"] += 0
                f_dhcp_pool["DHCP_Size"] += int(f_poolsize)
            #
        if f_dhcp_pool["DHCP_Size"] == 0:
            f_dhcp_pool["DHCP_Usage"] = "0%"
        else:
            f_dhcp_pool["DHCP_Usage"] = "{:.2f}%".format((f_dhcp_pool["Used_Lease"] / f_dhcp_pool["DHCP_Size"]) * 100)
        logging.info("Read DHCP pool completed.")
        return f_dhcp_pool


# This function retrieve terminal networks marked by distribute
def read_vlan_subnets(f_ipamclient):
    f_vlan_subnets = []
    logging.info("Reading VLAN subnets from IPAM......")

    f_select = "subnet_id,start_hostaddr,subnet_size,subnet_name,subnet_class_name,vlmvlan_vlan_id,vlmvlan_name,parent_subnet_name,parent_start_ip_addr,parent_subnet_size"
    f_read_net = {
        "SELECT": f_select,
        "WHERE": "site_id='2' and is_terminal='1' and vlmvlan_vlan_id='101'",
        "GROUPBY": ""
    }
    f_read_net_result = f_ipamclient.get("ip_block_subnet_groupby", f_read_net)
    #
    if f_read_net_result[0] != 200:
        logging.error(f"Could not read out network, error message: {f_read_net_result}. Please contact IPAM Admin.")
        return []
    else:
        logging.info("------ Read terminal network complete, sort and generate report -----")
        for f_net in f_read_net_result[1]:
            f_net_class = f_net.get('subnet_class_name')
            if "DISTRIBUTE" not in f_net_class.upper():
                continue

            f_startaddr = f_net.get('start_hostaddr')
            f_netsize = f"{int(f_net.get('subnet_size')) - 2}" if int(f_net.get('subnet_size')) >= 4 else int(f_net.get('subnet_size'))
            f_netaddr = f"{f_startaddr}/{size_to_prefix(int(f_net.get('subnet_size')))}"
            f_network = {
                "NET_ID": f_net.get('subnet_id'),
                "Name": f_net.get('subnet_name'),
                "NET_Addr": f_netaddr,
                "NET_Size": f_netsize,
                "VLAN_ID": f_net.get('vlmvlan_vlan_id'),
                "VLAN_Name": f_net.get('vlmvlan_name'),
                "Parent_Name": f_net.get('parent_subnet_name'),
                "Parent_Addr": "{}/{}".format(hex_to_ip(f_net.get('parent_start_ip_addr')), size_to_prefix(f_net.get('parent_subnet_size')))
            }
            # save to output
            f_vlan_subnets.append(f_network)
        logging.info("Read terminal network completed.")
        return f_vlan_subnets

### End of Function declaration ###


### Main body start ###
# Initiate logging
log_file = setup_logging()
open(log_file, 'w', encoding='UTF-8').close()
os.chmod(log_file, 0o644)
# Declare global variables, file path, logging path, files etc.
inventory_path = "/var/automation_file/Network_Inventory"
splunk_report = "/var/automation_log/splunk_log/network_inventory.log"
#
inventory_file = f"{inventory_path}/vlan101_dhcp_usage.csv"
#
# Set IPAM credential
usr, pwd = get_credential("IPAM-READ")
# Initiate IPAM client
ipamclient = IPAMClient("https://ipam.ikea.com", usr, pwd)  
# Read network from IPAM

vlan_networks = read_vlan_subnets(ipamclient)
# Generate terminal network output
if not vlan_networks:
    logging.error("No VLAN network found, please check IPAM.")
else:
    for network in vlan_networks:
        net_id = network.get("NET_ID")
        dhcp_info = read_dhcp_range(ipamclient, net_id)
        network.update(dhcp_info)

    # Create csv version terminal networks
    write_list_to_csv(vlan_networks, inventory_file)
    # Create splunk report
    open(splunk_report, 'w', encoding='UTF-8').close()
    os.chmod(splunk_report, 0o644)
    write_to_splunk(vlan_networks, splunk_report)

# Print EoP
logging.info("DHCP usage calculation for VLAN101 completed at {}".format(set_timestamp()))
print("DHCP usage calculation for VLAN101 completed at {}".format(set_timestamp()))
