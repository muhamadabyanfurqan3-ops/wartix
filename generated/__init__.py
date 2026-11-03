import os
import sys

# Memastikan direktori package ini ada di sys.path agar import antar-stub gRPC berjalan mulus
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from . import wartix_pb2
from . import wartix_pb2_grpc

__all__ = ["wartix_pb2", "wartix_pb2_grpc"]

