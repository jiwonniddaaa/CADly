import sqlite3
import pandas as pd

csv_path = "./mart_djy_02_clean.csv"
db_path = "./mart_building_data.db"

print("🔄 4. 총괄표제부(02) 적재 시작 (오버플로우 방어 모드)...")
conn = sqlite3.connect(db_path)
conn.execute("DROP TABLE IF EXISTS summary_records;")

for chunk in pd.read_csv(csv_path, chunksize=100000, dtype=str, low_memory=False):
    chunk.to_sql("summary_records", conn, if_exists="append", index=False)
    print(".", end="", flush=True)

print("\n⚡ 총괄표제부 인덱스 생성 중...")
conn.execute("CREATE INDEX IF NOT EXISTS idx_s_loc_pur ON summary_records (대지_위치, 주_용도_코드_명);")
conn.execute("CREATE INDEX IF NOT EXISTS idx_s_pk ON summary_records (관리_건축물대장_PK);")
conn.commit()
conn.close()
print("✅ 총괄표제부 최종 적재 완료! 대규모 파일 데이터베이스 완공.")