# ipam_sdk/utils/ipam_client.py
import httpx
import logging
import urllib3
import json
import time
import hashlib
import asyncio
from typing import Optional

class IPAMClient:
    def __init__(self, base_url: str, usr: Optional[str] = None, pwd: Optional[str] = None, 
                 token: Optional[str] = None, secret: Optional[str] = None, debug: bool = False):
        """
        Initialize IPAM Client with either username/password or API token authentication.
        
        Args:
            base_url: IPAM server base URL
            usr: Username for basic auth (required if not using token)
            pwd: Password for basic auth (required if not using token)
            token: API token for SDS auth (required if not using usr/pwd)
            secret: API secret for SDS auth (required if using token)
            debug: Enable debug logging
        """
        self.base_url = base_url
        self.debug = debug
        #self.session = requests.Session()
        self.session = httpx.AsyncClient(
            http2=True,
            verify=False,
            timeout=httpx.Timeout(connect=10.0, read=900.0, write=900.0, pool=900.0),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=20,
                keepalive_expiry=300.0  # Keep connections alive for 5 minutes
            )
        )  # Enhanced configuration for firewall keepalive and long queries
        self.auth_type = None
        
        # Authentication setup
        if token and secret:
            # API token authentication
            self.token = token
            self.secret = secret
            self.auth_type = "token"
            self.session.headers.update({
                "cache-control": "no-cache",
                "Connection": "keep-alive"
            })
        elif usr and pwd:
            # Username/password authentication
            self.auth_type = "basic"
            self.session.headers.update({
                "X-IPM-Username": usr,
                "X-IPM-Password": pwd,
                "cache-control": "no-cache",
                "Connection": "keep-alive"
            })
        else:
            raise ValueError("Either (usr, pwd) or (token, secret) must be provided for authentication")
        
        urllib3.disable_warnings()
        self.logger = logging.getLogger(__name__)
        
        if self.debug:
            self.logger.debug(f"IPAMClient initialized with base_url: {base_url}")
            self.logger.debug(f"Authentication type: {self.auth_type}")
            if self.auth_type == "basic":
                self.logger.debug(f"Session headers: {dict(self.session.headers)}")
            else:
                self.logger.debug("Using API token authentication")

    def _generate_sds_signature(self, method: str, url: str, timestamp: int) -> str:
        """
        Generate SDS signature for API token authentication.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL for the request
            timestamp: Unix timestamp in seconds
            
        Returns:
            SHA3-256 hash signature
        """
        string_to_sign = f"{self.secret}\n{timestamp}\n{method.upper()}\n{url}"
        signature = hashlib.sha3_256(string_to_sign.encode('utf-8')).hexdigest()
        
        if self.debug:
            self.logger.debug(f"StringToSign: {repr(string_to_sign)}")
            self.logger.debug(f"Generated signature: {signature}")
            
        return signature
    
    def _prepare_headers_for_request(self, method: str, url: str) -> dict:
        """
        Prepare headers for the request based on authentication type.
        
        Args:
            method: HTTP method
            url: Full URL for the request
            
        Returns:
            Dictionary of headers to add to the request
        """
        headers = {
            # TCP keepalive headers to prevent firewall idle timeouts
            "Keep-Alive": "timeout=300, max=1000",  # 5 min timeout, max 1000 requests per connection
            "Connection": "keep-alive"
        }
        
        if self.auth_type == "token":
            timestamp = int(time.time())
            signature = self._generate_sds_signature(method, url, timestamp)
            
            headers.update({
                "X-SDS-TS": str(timestamp),
                "Authorization": f"SDS {self.token}:{signature}"
            })
            
            if self.debug:
                self.logger.debug(f"SDS headers - X-SDS-TS: {timestamp}, Authorization: SDS {self.token}:{signature}")
        
        return headers

    async def _request(self, method, api_call, input_param, rpc=False):
        query_url = f"{self.base_url}/{'rpc' if rpc else 'rest'}/{api_call}"
        
        # Prepare authentication headers for this specific request
        request_headers = self._prepare_headers_for_request(method.upper(), query_url)
        
        if self.debug:
            self.logger.debug(f"Making {method.upper()} request to: {query_url}")
            self.logger.debug(f"Parameters: {input_param}")
            self.logger.debug(f"RPC mode: {rpc}")
            if request_headers:
                self.logger.debug(f"Request-specific headers: {request_headers}")
        
        # Retry logic for firewall connection issues
        max_retries = 3
        retry_delay = 1  # Start with 1 second delay
        
        for attempt in range(max_retries + 1):
            try:
                response = await getattr(self.session, method)(
                    query_url,
                    params=input_param,
                    headers=request_headers
                )
                break  # Success - exit retry loop

            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError,
                   httpx.RemoteProtocolError, httpx.ConnectError) as conn_err:
                if attempt < max_retries:
                    if self.debug:
                        self.logger.debug(f"Connection attempt {attempt + 1} failed: {conn_err}. Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    self.logger.error(f"Connection failed after {max_retries + 1} attempts: {conn_err}")
                    return "503", f"Connection error after retries: {conn_err}"
        
        try:
            
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
                    
        except httpx.HTTPStatusError as http_err:
            self.logger.error(f"HTTP error occurred: Code: {http_err.response.status_code}")
            if self.debug:
                self.logger.debug(f"HTTP error response: {http_err.response.text}")
            return http_err.response.status_code, f"HTTP error occurred: {http_err}"
        except httpx.RequestError as req_err:
            self.logger.error(f"Request error occurred: {req_err}")
            if self.debug:
                self.logger.debug(f"Request exception details: {type(req_err).__name__}: {req_err}")
            return "500", f"Request error occurred: {req_err}"
        except Exception as err:
            self.logger.error(f"An error occurred: {err}")
            if self.debug:
                self.logger.debug(f"Exception details: {type(err).__name__}: {err}")
            return "500", f"An error occurred: {err}"
        
        if self.debug:
            self.logger.debug(f"Request completed successfully with status: {response_code}")
            
        return response_code, query_response

    async def get(self, api_call, input_param):
        return await self._request("get", api_call, input_param)

    async def post(self, api_call, input_param):
        return await self._request("post", api_call, input_param)

    async def put(self, api_call, input_param):
        return await self._request("put", api_call, input_param)

    async def delete(self, api_call, input_param):
        return await self._request("delete", api_call, input_param)

    async def rpc(self, api_call, input_param):
        return await self._request("options", api_call, input_param, rpc=True)

    async def close(self):
        await self.session.aclose()
