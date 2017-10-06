import os
import os.path
import sys
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="## %(levelname)s ## %(threadName)s ## %(message)s"
    )
sys.path.append(os.path.join(os.getcwd(), '.'))
