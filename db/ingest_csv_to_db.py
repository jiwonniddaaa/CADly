import sqlite3
import pandas as pd

csv_path = "./mart_djy_03_clean.csv"
db_path = "./mart_building_data.db"

print("🔄 1. 표제부(03) 적재 시작 (오버플로우 방어 모드)...")
conn = sqlite3.connect(db_path)
conn.execute("DROP TABLE IF EXISTS building_records;")

# dtype=str을 주어 모든 컬럼을 문자열로 읽어 오버플로우를 원천 차단합니다.
for chunk in pd.read_csv(csv_path, chunksize=100000, dtype=str, low_memory=False):
    chunk.to_sql("building_records", conn, if_exists="append", index=False)
    print(".", end="", flush=True)

print("\n⚡ 표제부 복합 인덱스 생성 중...")
conn.execute("CREATE INDEX IF NOT EXISTS idx_b_loc_pur ON building_records (대지_위치, 주_용도_코드_명);")
conn.commit()
conn.close()
print("✅ 표제부 적재 완료!")