import sqlite3
import pandas as pd

csv_path = "./mart_djy_09_clean.csv"
db_path = "./mart_building_data.db"

print("🔄 3. 전유부(09) 적재 시작 (오버플로우 방어 모드)...")
conn = sqlite3.connect(db_path)
conn.execute("DROP TABLE IF EXISTS private_records;")

for chunk in pd.read_csv(csv_path, chunksize=100000, dtype=str, low_memory=False):
    chunk.to_sql("private_records", conn, if_exists="append", index=False)
    print(".", end="", flush=True)

print("\n⚡ 전유부 인덱스 생성 중...")
conn.execute("CREATE INDEX IF NOT EXISTS idx_p_loc_type ON private_records (대지_위치, 대장_종류_코드_명);")
conn.execute("CREATE INDEX IF NOT EXISTS idx_p_pk ON private_records (관리_건축물대장_PK);")
conn.commit()
conn.close()
print("✅ 전유부 적재 완료!")