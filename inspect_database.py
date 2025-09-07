#!/usr/bin/env python3
"""
Database Inspector Script for monolith.db
This script inspects the core tables and generates a comprehensive schema output
for building a Django-based CRM system.
"""

import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd

class DatabaseInspector:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
        self.cursor = None
        
    def connect(self):
        """Establish connection to the SQLite database"""
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.cursor = self.connection.cursor()
            print(f"✅ Successfully connected to {self.db_path}")
        except sqlite3.Error as e:
            print(f"❌ Error connecting to database: {e}")
            raise
    
    def disconnect(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            print("✅ Database connection closed")
    
    def get_table_list(self) -> List[str]:
        """Get list of all tables in the database"""
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in self.cursor.fetchall()]
        return tables
    
    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Get detailed schema information for a specific table"""
        # Get column information
        self.cursor.execute(f"PRAGMA table_info({table_name});")
        columns = self.cursor.fetchall()
        
        # Get foreign key information
        self.cursor.execute(f"PRAGMA foreign_key_list({table_name});")
        foreign_keys = self.cursor.fetchall()
        
        # Get index information
        self.cursor.execute(f"PRAGMA index_list({table_name});")
        indexes = self.cursor.fetchall()
        
        # Get sample data (first 5 rows)
        try:
            self.cursor.execute(f"SELECT * FROM {table_name} LIMIT 5;")
            sample_data = self.cursor.fetchall()
            column_names = [description[0] for description in self.cursor.description]
        except sqlite3.Error:
            sample_data = []
            column_names = []
        
        # Get row count
        self.cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        row_count = self.cursor.fetchone()[0]
        
        # Parse column information
        column_info = []
        for col in columns:
            col_dict = {
                'name': col[1],
                'type': col[2],
                'not_null': bool(col[3]),
                'default_value': col[4],
                'primary_key': bool(col[5])
            }
            column_info.append(col_dict)
        
        # Parse foreign key information
        fk_info = []
        for fk in foreign_keys:
            fk_dict = {
                'column': fk[3],
                'references_table': fk[2],
                'references_column': fk[4],
                'on_update': fk[5],
                'on_delete': fk[6]
            }
            fk_info.append(fk_dict)
        
        # Parse index information
        index_info = []
        for idx in indexes:
            idx_dict = {
                'name': idx[1],
                'unique': bool(idx[2]),
                'origin': idx[3]
            }
            index_info.append(idx_dict)
        
        return {
            'table_name': table_name,
            'row_count': row_count,
            'columns': column_info,
            'foreign_keys': fk_info,
            'indexes': index_info,
            'sample_data': {
                'columns': column_names,
                'rows': sample_data
            }
        }
    
    def get_relationships(self, tables: List[str]) -> Dict[str, List[Dict]]:
        """Analyze relationships between tables"""
        relationships = {}
        
        for table in tables:
            relationships[table] = []
            try:
                schema = self.get_table_schema(table)
                for fk in schema['foreign_keys']:
                    relationships[table].append({
                        'type': 'foreign_key',
                        'local_column': fk['column'],
                        'references_table': fk['references_table'],
                        'references_column': fk['references_column'],
                        'on_update': fk['on_update'],
                        'on_delete': fk['on_delete']
                    })
            except sqlite3.Error as e:
                print(f"⚠️  Warning: Could not analyze relationships for {table}: {e}")
        
        return relationships
    
    def inspect_core_tables(self, core_tables: List[str]) -> Dict[str, Any]:
        """Inspect the core tables specified for the CRM"""
        print(f"\n🔍 Inspecting core tables: {', '.join(core_tables)}")
        
        all_tables = self.get_table_list()
        missing_tables = [table for table in core_tables if table not in all_tables]
        
        if missing_tables:
            print(f"⚠️  Warning: The following tables were not found: {missing_tables}")
        
        existing_tables = [table for table in core_tables if table in all_tables]
        
        inspection_results = {
            'inspection_date': datetime.now().isoformat(),
            'database_path': self.db_path,
            'core_tables': core_tables,
            'missing_tables': missing_tables,
            'existing_tables': existing_tables,
            'table_schemas': {},
            'relationships': {},
            'summary': {}
        }
        
        # Inspect each existing table
        for table in existing_tables:
            print(f"  📋 Analyzing {table}...")
            try:
                schema = self.get_table_schema(table)
                inspection_results['table_schemas'][table] = schema
                print(f"    ✅ {table}: {schema['row_count']} rows, {len(schema['columns'])} columns")
            except sqlite3.Error as e:
                print(f"    ❌ Error analyzing {table}: {e}")
                inspection_results['table_schemas'][table] = {'error': str(e)}
        
        # Analyze relationships
        print(f"\n🔗 Analyzing table relationships...")
        inspection_results['relationships'] = self.get_relationships(existing_tables)
        
        # Generate summary
        inspection_results['summary'] = self.generate_summary(inspection_results)
        
        return inspection_results
    
    def generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a summary of the database inspection"""
        summary = {
            'total_tables_found': len(results['existing_tables']),
            'total_tables_missing': len(results['missing_tables']),
            'total_columns': 0,
            'total_rows': 0,
            'tables_with_data': 0,
            'key_insights': []
        }
        
        for table, schema in results['table_schemas'].items():
            if 'error' not in schema:
                summary['total_columns'] += len(schema['columns'])
                summary['total_rows'] += schema['row_count']
                if schema['row_count'] > 0:
                    summary['tables_with_data'] += 1
                
                # Add insights
                if schema['row_count'] > 10000:
                    summary['key_insights'].append(f"{table} has {schema['row_count']:,} rows - large dataset")
                
                primary_keys = [col['name'] for col in schema['columns'] if col['primary_key']]
                if primary_keys:
                    summary['key_insights'].append(f"{table} primary key: {', '.join(primary_keys)}")
                
                foreign_keys = len(schema['foreign_keys'])
                if foreign_keys > 0:
                    summary['key_insights'].append(f"{table} has {foreign_keys} foreign key relationship(s)")
        
        return summary
    
    def export_to_json(self, results: Dict[str, Any], filename: str = None):
        """Export inspection results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"database_schema_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"📄 Schema exported to {filename}")
        return filename
    
    def print_schema_report(self, results: Dict[str, Any]):
        """Print a formatted schema report to console"""
        print("\n" + "="*80)
        print("📊 DATABASE SCHEMA INSPECTION REPORT")
        print("="*80)
        
        print(f"\n📅 Inspection Date: {results['inspection_date']}")
        print(f"🗄️  Database: {results['database_path']}")
        print(f"📋 Core Tables: {len(results['core_tables'])}")
        print(f"✅ Found: {len(results['existing_tables'])}")
        print(f"❌ Missing: {len(results['missing_tables'])}")
        
        if results['missing_tables']:
            print(f"\n⚠️  Missing Tables: {', '.join(results['missing_tables'])}")
        
        print(f"\n📈 SUMMARY:")
        summary = results['summary']
        print(f"  • Total Columns: {summary['total_columns']}")
        print(f"  • Total Rows: {summary['total_rows']:,}")
        print(f"  • Tables with Data: {summary['tables_with_data']}")
        
        if summary['key_insights']:
            print(f"\n💡 KEY INSIGHTS:")
            for insight in summary['key_insights']:
                print(f"  • {insight}")
        
        print(f"\n📋 TABLE DETAILS:")
        print("-" * 80)
        
        for table, schema in results['table_schemas'].items():
            if 'error' in schema:
                print(f"\n❌ {table.upper()}: ERROR - {schema['error']}")
                continue
            
            print(f"\n📊 {table.upper()}")
            print(f"  Rows: {schema['row_count']:,}")
            print(f"  Columns: {len(schema['columns'])}")
            
            print(f"\n  📝 COLUMNS:")
            for col in schema['columns']:
                pk_marker = " 🔑" if col['primary_key'] else ""
                nn_marker = " ⚠️" if col['not_null'] else ""
                default_marker = f" (default: {col['default_value']})" if col['default_value'] else ""
                print(f"    • {col['name']}: {col['type']}{pk_marker}{nn_marker}{default_marker}")
            
            if schema['foreign_keys']:
                print(f"\n  🔗 FOREIGN KEYS:")
                for fk in schema['foreign_keys']:
                    print(f"    • {fk['column']} → {fk['references_table']}.{fk['references_column']}")
            
            if schema['indexes']:
                print(f"\n  📇 INDEXES:")
                for idx in schema['indexes']:
                    unique_marker = " (unique)" if idx['unique'] else ""
                    print(f"    • {idx['name']}{unique_marker}")
            
            # Show sample data if available
            if schema['sample_data']['rows']:
                print(f"\n  📄 SAMPLE DATA (first 5 rows):")
                df = pd.DataFrame(schema['sample_data']['rows'], columns=schema['sample_data']['columns'])
                print(df.to_string(index=False, max_cols=10))
        
        print("\n" + "="*80)

def main():
    """Main function to run the database inspection"""
    # Core tables for the CRM
    core_tables = [
        'ProviderBill',
        'BillLineItem', 
        'orders',
        'order_line_items',
        'dim_proc',
        'ppo',
        'providers',
        'ota'
    ]
    
    db_path = "monolith.db"
    
    print("🚀 Starting Database Inspection for Django CRM")
    print(f"📁 Database: {db_path}")
    print(f"🎯 Core Tables: {', '.join(core_tables)}")
    
    inspector = DatabaseInspector(db_path)
    
    try:
        # Connect to database
        inspector.connect()
        
        # Inspect core tables
        results = inspector.inspect_core_tables(core_tables)
        
        # Print formatted report
        inspector.print_schema_report(results)
        
        # Export to JSON
        json_file = inspector.export_to_json(results)
        
        print(f"\n✅ Inspection complete! Results saved to {json_file}")
        
    except Exception as e:
        print(f"❌ Error during inspection: {e}")
        raise
    finally:
        inspector.disconnect()

if __name__ == "__main__":
    main()
