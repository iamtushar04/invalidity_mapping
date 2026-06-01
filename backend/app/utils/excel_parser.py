import pandas as pd
import logging
from typing import List, BinaryIO

logger = logging.getLogger(__name__)

class ExcelParser:
    def parse_patent_numbers(self, file_content: BinaryIO) -> List[str]:
        try:
            # Read first worksheet using pandas
            df = pd.read_excel(file_content, header=None)
            
            # Extract first column (Column A) and discard null values
            first_col = df.iloc[:, 0].dropna()
            
            # Format and sanitize values as string
            numbers = [str(x).strip() for x in first_col.values]
            
            # Remove header if common label matches
            if numbers and any(label in numbers[0].lower() for label in ["patent", "number", "id", "ref"]):
                numbers = numbers[1:]
                
            return [n for n in numbers if n]
        except Exception as e:
            logger.error(f"Failed to parse excel file: {e}")
            return []

excel_parser = ExcelParser()
