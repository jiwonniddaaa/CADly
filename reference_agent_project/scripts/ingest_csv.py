import argparse
from app.services.csv_ingestion import CsvIngestionService

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', required=True)
    args = parser.parse_args()
    result = CsvIngestionService().ingest_csv(args.csv)
    print(result)
