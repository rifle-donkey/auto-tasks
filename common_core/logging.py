# ipam_sdk/utils/logging.py
import logging
import sys

def setup_logging(log_file, debug=False):
    datefmt = '%Y-%m-%d %H:%M:%S'
    
    # Set log level based on debug flag
    log_level = logging.DEBUG if debug else logging.INFO
    
    # Configure werkzeug logging (for web frameworks)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    
    # Configure urllib3 logging for HTTP requests
    if debug:
        logging.getLogger('urllib3').setLevel(logging.DEBUG)
        logging.getLogger('requests').setLevel(logging.DEBUG)
    else:
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('requests').setLevel(logging.WARNING)
    
    # Create formatters
    if debug:
        formatter = logging.Formatter(
            '%(asctime)s %(name)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s',
            datefmt=datefmt
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s %(message)s',
            datefmt=datefmt
        )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add file handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Add console handler for debug mode
    if debug:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)