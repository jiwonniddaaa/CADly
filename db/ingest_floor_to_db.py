import sqlite3
import pandas as pd

csv_path = "./mart_djy_04_clean.csv"
db_path = "./mart_building_data.db"

print("🔄 2. 층별개요(04) 적재 시작 (오버플로우 방어 모드)...")
conn = sqlite3.connect(db_path)
conn.execute("DROP TABLE IF EXISTS floor_records;")

for chunk in pd.read_csv(csv_path, chunksize=100000, dtype=str, low_memory=False):
    chunk.to_sql("floor_records", conn, if_exists="append", index=False)
    print(".", end="", flush=True)

print("\n⚡ 층별개요 인덱스 생성 중...")
conn.execute("CREATE INDEX IF NOT EXISTS idx_f_loc_pur ON floor_records (대지_위치, 주_용도_코드_명);")
conn.execute("CREATE INDEX IF NOT EXISTS idx_f_pk ON floor_records (관리_건축물대장_PK);")
conn.commit()
conn.close()
print("✅ 층별개요 적재 완료!")