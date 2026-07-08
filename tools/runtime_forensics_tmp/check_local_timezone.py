import time
from datetime import datetime, timezone

print("Local time:", datetime.now().isoformat())
print("UTC time  :", datetime.now(timezone.utc).isoformat())
print("Timezone  :", time.tzname)
