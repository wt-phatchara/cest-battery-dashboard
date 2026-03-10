import pandas as pd  # pyre-ignore
import NewareNDA     # pyre-ignore
import uuid

def test():
    try:
        print(f"Pandas version: {pd.__version__}")
        print(f"NewareNDA imported successfully")
        
        unique_hex = str(uuid.uuid4().hex)
        print(f"unique_hex type: {type(unique_hex)}")
        unique_id = unique_hex[0:8]  # pyre-ignore
        print(f"unique_id: {unique_id}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
