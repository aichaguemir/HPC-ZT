import logging


def setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('gateway.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("hpc_gateway")


logger = setup_logging()
