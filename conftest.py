"""让测试能直接 import 到项目根目录下的 fin_audit 包。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
