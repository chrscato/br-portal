#!/usr/bin/env python3
"""
Log Viewer Utility
Provides easy access to job logs with filtering and search capabilities
"""

import os
import sys
import glob
import json
from datetime import datetime, timedelta
from pathlib import Path
import argparse


def list_recent_logs(days=7, job_type=None):
    """List recent log files"""
    logs_dir = Path("logs")
    if not logs_dir.exists():
        print("❌ No logs directory found. Run some jobs first!")
        return []
    
    # Get all log files
    pattern = f"*_{job_type}_*.log" if job_type else "*.log"
    log_files = list(logs_dir.glob(pattern))
    
    # Filter by date
    cutoff_date = datetime.now() - timedelta(days=days)
    recent_logs = []
    
    for log_file in log_files:
        try:
            # Extract timestamp from filename (last part before .log)
            timestamp_str = log_file.stem.split('_')[-1]
            timestamp = datetime.fromtimestamp(int(timestamp_str))
            
            if timestamp >= cutoff_date:
                recent_logs.append((log_file, timestamp))
        except (ValueError, IndexError):
            # Skip files that don't match expected format
            continue
    
    # Sort by timestamp (newest first)
    recent_logs.sort(key=lambda x: x[1], reverse=True)
    
    return recent_logs


def show_log_summary(log_file):
    """Show a summary of a log file"""
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        error_lines = [line for line in lines if 'ERROR' in line or '❌' in line]
        warning_lines = [line for line in lines if 'WARNING' in line or '⚠️' in line]
        success_lines = [line for line in lines if '✅' in line or 'Successfully' in line]
        
        print(f"📄 Log File: {log_file.name}")
        print(f"📊 Total Lines: {total_lines}")
        print(f"✅ Success Messages: {len(success_lines)}")
        print(f"⚠️  Warnings: {len(warning_lines)}")
        print(f"❌ Errors: {len(error_lines)}")
        
        if error_lines:
            print(f"\n🔍 Recent Errors:")
            for error in error_lines[-3:]:  # Show last 3 errors
                print(f"   {error.strip()}")
        
        return {
            'total_lines': total_lines,
            'errors': len(error_lines),
            'warnings': len(warning_lines),
            'successes': len(success_lines)
        }
        
    except Exception as e:
        print(f"❌ Error reading log file: {e}")
        return None


def search_logs(search_term, job_type=None, days=7):
    """Search for specific terms in recent logs"""
    recent_logs = list_recent_logs(days, job_type)
    
    if not recent_logs:
        print("❌ No recent logs found")
        return
    
    print(f"🔍 Searching for '{search_term}' in recent logs...")
    print("=" * 60)
    
    found_matches = 0
    
    for log_file, timestamp in recent_logs:
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            matching_lines = []
            for i, line in enumerate(lines, 1):
                if search_term.lower() in line.lower():
                    matching_lines.append((i, line.strip()))
            
            if matching_lines:
                found_matches += len(matching_lines)
                print(f"\n📄 {log_file.name} ({timestamp.strftime('%Y-%m-%d %H:%M:%S')})")
                print(f"   Found {len(matching_lines)} matches:")
                
                for line_num, line_content in matching_lines[-5:]:  # Show last 5 matches
                    print(f"   Line {line_num}: {line_content}")
                
                if len(matching_lines) > 5:
                    print(f"   ... and {len(matching_lines) - 5} more matches")
        
        except Exception as e:
            print(f"❌ Error reading {log_file.name}: {e}")
    
    print(f"\n🎯 Total matches found: {found_matches}")


def view_live_log(log_file):
    """View a log file in real-time (like tail -f)"""
    try:
        print(f"👀 Watching {log_file.name} for new entries...")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        # Show last 10 lines first
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-10:]:
                print(line.rstrip())
        
        # Then follow new lines
        import time
        with open(log_file, 'r', encoding='utf-8') as f:
            f.seek(0, 2)  # Go to end of file
            
            while True:
                line = f.readline()
                if line:
                    print(line.rstrip())
                else:
                    time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\n👋 Stopped watching log file")
    except Exception as e:
        print(f"❌ Error watching log file: {e}")


def main():
    parser = argparse.ArgumentParser(description="View and search job logs")
    parser.add_argument('--list', '-l', action='store_true', help='List recent log files')
    parser.add_argument('--days', '-d', type=int, default=7, help='Number of days to look back (default: 7)')
    parser.add_argument('--type', '-t', choices=['process_scans', 'process_second_pass', 'upload_batch', 'process_mapping', 'process_validation'], help='Filter by job type')
    parser.add_argument('--search', '-s', help='Search for specific term in logs')
    parser.add_argument('--view', '-v', help='View specific log file')
    parser.add_argument('--watch', '-w', help='Watch a log file in real-time')
    parser.add_argument('--summary', help='Show summary of specific log file')
    
    args = parser.parse_args()
    
    if args.list:
        recent_logs = list_recent_logs(args.days, args.type)
        
        if not recent_logs:
            print("❌ No recent logs found")
            return
        
        print(f"📋 Recent log files (last {args.days} days):")
        print("=" * 80)
        
        for log_file, timestamp in recent_logs:
            job_type = log_file.stem.split('_')[0] if '_' in log_file.stem else 'unknown'
            print(f"📄 {log_file.name}")
            print(f"   Type: {job_type}")
            print(f"   Date: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Size: {log_file.stat().st_size} bytes")
            print()
    
    elif args.search:
        search_logs(args.search, args.type, args.days)
    
    elif args.view:
        log_file = Path("logs") / args.view
        if not log_file.exists():
            print(f"❌ Log file not found: {log_file}")
            return
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                print(f"📄 Contents of {log_file.name}:")
                print("=" * 80)
                print(f.read())
        except Exception as e:
            print(f"❌ Error reading log file: {e}")
    
    elif args.watch:
        log_file = Path("logs") / args.watch
        if not log_file.exists():
            print(f"❌ Log file not found: {log_file}")
            return
        
        view_live_log(log_file)
    
    elif args.summary:
        log_file = Path("logs") / args.summary
        if not log_file.exists():
            print(f"❌ Log file not found: {log_file}")
            return
        
        show_log_summary(log_file)
    
    else:
        # Default: show recent logs
        recent_logs = list_recent_logs(args.days, args.type)
        
        if not recent_logs:
            print("❌ No recent logs found")
            print("💡 Run some job operations to generate logs!")
            return
        
        print(f"📋 Recent log files (last {args.days} days):")
        print("=" * 80)
        
        for log_file, timestamp in recent_logs[:10]:  # Show top 10
            job_type = log_file.stem.split('_')[0] if '_' in log_file.stem else 'unknown'
            print(f"📄 {log_file.name} ({job_type}) - {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if len(recent_logs) > 10:
            print(f"... and {len(recent_logs) - 10} more files")
        
        print(f"\n💡 Use --help to see all available options")


if __name__ == "__main__":
    main()
