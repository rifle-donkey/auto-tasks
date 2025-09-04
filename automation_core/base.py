# ipam_client/base.py
import requests
import logging
import json

class IPAMClient:
    def __init__(self, base_url, usr, pwd, debug=False):
        self.base_url = base_url
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update({
            "X-IPM-Username": usr,
            "X-IPM-Password": pwd,
            "cache-control": "no-cache"
        })
        requests.packages.urllib3.disable_warnings()
        self.logger = logging.getLogger(__name__)
        
        if self.debug:
            self.logger.debug(f"IPAMClient initialized with base_url: {base_url}")
            self.logger.debug(f"Session headers: {dict(self.session.headers)}")

    def _request(self, method, api_call, input_param, rpc=False):
        query_url = f"{self.base_url}/{'rpc' if rpc else 'rest'}/{api_call}"
        
        if self.debug:
            self.logger.debug(f"Making {method.upper()} request to: {query_url}")
            self.logger.debug(f"Parameters: {input_param}")
            self.logger.debug(f"RPC mode: {rpc}")
        
        try:
            response = getattr(self.session, method)(
                query_url,
                params=input_param,
                timeout=900,
                verify=False
            )
            
            if self.debug:
                self.logger.debug(f"Response status code: {response.status_code}")
                self.logger.debug(f"Response headers: {dict(response.headers)}")
                self.logger.debug(f"Response content length: {len(response.content)}")
                
                # Log response content (truncated for readability)
                try:
                    response_text = response.text
                    if len(response_text) > 1000:
                        self.logger.debug(f"Response content (truncated): {response_text[:1000]}...")
                    else:
                        self.logger.debug(f"Response content: {response_text}")
                except Exception as e:
                    self.logger.debug(f"Could not log response content: {e}")
            
            response.raise_for_status()
            response_code = response.status_code
            query_response = response.json() if response_code in [200, 201, 400] else response.text
            
            if self.debug:
                if isinstance(query_response, dict):
                    self.logger.debug(f"Parsed JSON response: {json.dumps(query_response, indent=2)}")
                else:
                    self.logger.debug(f"Text response: {query_response}")
                    
        except requests.exceptions.HTTPError as http_err:
            self.logger.error(f"HTTP error occurred: Code: {http_err.response.status_code}")
            if self.debug:
                self.logger.debug(f"HTTP error response: {http_err.response.text}")
            return http_err.response.status_code, f"HTTP error occurred: {http_err}"
        except requests.exceptions.RequestException as req_err:
            self.logger.error(f"Request error occurred: {req_err}")
            if self.debug:
                self.logger.debug(f"Request exception details: {type(req_err).__name__}: {req_err}")
            return getattr(req_err.response, 'status_code', '500'), f"Request error occurred: {req_err}"
        except Exception as err:
            self.logger.error(f"An error occurred: {err}")
            if self.debug:
                self.logger.debug(f"Exception details: {type(err).__name__}: {err}")
            return "500", f"An error occurred: {err}"
        
        if self.debug:
            self.logger.debug(f"Request completed successfully with status: {response_code}")
            
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
