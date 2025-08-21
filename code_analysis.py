#!/usr/bin/env python3
"""
Code Analysis Script for BMLibrarian

Traverses the application directory structure and counts:
- Lines of Python code (with and without comments)
- Number of files, classes, and functions
- Longest and median sizes for classes, functions, and files
"""

import ast
import os
import statistics
from pathlib import Path
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass


@dataclass
class FileStats:
    """Statistics for a single Python file."""
    path: str
    total_lines: int
    code_lines: int
    comment_lines: int
    blank_lines: int
    classes: List[Tuple[str, int]]  # (name, line_count)
    functions: List[Tuple[str, int]]  # (name, line_count)


@dataclass
class CodebaseStats:
    """Overall codebase statistics."""
    total_files: int
    total_lines: int
    total_code_lines: int
    total_comment_lines: int
    total_blank_lines: int
    total_classes: int
    total_functions: int
    file_stats: List[FileStats]


class CodeAnalyzer:
    """Analyzes Python code to extract statistics."""
    
    def __init__(self, root_dir: str = "src"):
        self.root_dir = Path(root_dir)
        self.file_stats: List[FileStats] = []
    
    def analyze_file(self, file_path: Path) -> FileStats:
        """Analyze a single Python file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.splitlines()
        total_lines = len(lines)
        
        # Count comment and blank lines
        comment_lines = 0
        blank_lines = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank_lines += 1
            elif stripped.startswith('#'):
                comment_lines += 1
        
        code_lines = total_lines - comment_lines - blank_lines
        
        # Parse AST to find classes and functions
        classes = []
        functions = []
        
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_lines = self._count_node_lines(node, lines)
                    classes.append((node.name, class_lines))
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    # Only count top-level functions and methods
                    if self._is_top_level_or_method(node, tree):
                        func_lines = self._count_node_lines(node, lines)
                        functions.append((node.name, func_lines))
        except SyntaxError:
            # Skip files with syntax errors
            pass
        
        return FileStats(
            path=str(file_path.relative_to(self.root_dir.parent)),
            total_lines=total_lines,
            code_lines=code_lines,
            comment_lines=comment_lines,
            blank_lines=blank_lines,
            classes=classes,
            functions=functions
        )
    
    def _count_node_lines(self, node: ast.AST, lines: List[str]) -> int:
        """Count the number of lines in an AST node."""
        if hasattr(node, 'end_lineno') and node.end_lineno:
            return node.end_lineno - node.lineno + 1
        else:
            # Fallback: estimate based on indentation
            start_line = node.lineno - 1
            indent_level = len(lines[start_line]) - len(lines[start_line].lstrip())
            
            line_count = 1
            for i in range(start_line + 1, len(lines)):
                line = lines[i]
                if line.strip():  # Non-empty line
                    current_indent = len(line) - len(line.lstrip())
                    if current_indent <= indent_level and not line.strip().startswith(('"""', "'''")):
                        break
                line_count += 1
            
            return line_count
    
    def _is_top_level_or_method(self, node: ast.FunctionDef, tree: ast.AST) -> bool:
        """Check if function is top-level or a class method."""
        for parent in ast.walk(tree):
            if isinstance(parent, ast.ClassDef):
                if node in parent.body:
                    return True
            elif isinstance(parent, ast.Module):
                if node in parent.body:
                    return True
        return False
    
    def analyze_directory(self) -> CodebaseStats:
        """Analyze all Python files in the directory."""
        python_files = list(self.root_dir.rglob("*.py"))
        
        for file_path in python_files:
            try:
                file_stat = self.analyze_file(file_path)
                self.file_stats.append(file_stat)
            except Exception as e:
                print(f"Warning: Could not analyze {file_path}: {e}")
        
        # Calculate totals
        total_files = len(self.file_stats)
        total_lines = sum(fs.total_lines for fs in self.file_stats)
        total_code_lines = sum(fs.code_lines for fs in self.file_stats)
        total_comment_lines = sum(fs.comment_lines for fs in self.file_stats)
        total_blank_lines = sum(fs.blank_lines for fs in self.file_stats)
        total_classes = sum(len(fs.classes) for fs in self.file_stats)
        total_functions = sum(len(fs.functions) for fs in self.file_stats)
        
        return CodebaseStats(
            total_files=total_files,
            total_lines=total_lines,
            total_code_lines=total_code_lines,
            total_comment_lines=total_comment_lines,
            total_blank_lines=total_blank_lines,
            total_classes=total_classes,
            total_functions=total_functions,
            file_stats=self.file_stats
        )


def print_statistics(stats: CodebaseStats):
    """Print formatted statistics."""
    print("=" * 60)
    print("BMLIBRARIAN CODEBASE ANALYSIS")
    print("=" * 60)
    
    # Overall statistics
    print(f"\nOVERALL STATISTICS:")
    print(f"  Total files:        {stats.total_files:,}")
    print(f"  Total lines:        {stats.total_lines:,}")
    print(f"  Code lines:         {stats.total_code_lines:,}")
    print(f"  Comment lines:      {stats.total_comment_lines:,}")
    print(f"  Blank lines:        {stats.total_blank_lines:,}")
    print(f"  Total classes:      {stats.total_classes:,}")
    print(f"  Total functions:    {stats.total_functions:,}")
    
    # Percentages
    if stats.total_lines > 0:
        code_pct = (stats.total_code_lines / stats.total_lines) * 100
        comment_pct = (stats.total_comment_lines / stats.total_lines) * 100
        blank_pct = (stats.total_blank_lines / stats.total_lines) * 100
        
        print(f"\nLINE BREAKDOWN:")
        print(f"  Code:     {code_pct:5.1f}%")
        print(f"  Comments: {comment_pct:5.1f}%")
        print(f"  Blank:    {blank_pct:5.1f}%")
    
    # File statistics
    file_sizes = [fs.total_lines for fs in stats.file_stats]
    if file_sizes:
        print(f"\nFILE STATISTICS:")
        print(f"  Largest file:       {max(file_sizes):,} lines")
        print(f"  Smallest file:      {min(file_sizes):,} lines")
        print(f"  Median file size:   {statistics.median(file_sizes):,.0f} lines")
        print(f"  Average file size:  {statistics.mean(file_sizes):,.1f} lines")
    
    # Class statistics
    all_classes = []
    for fs in stats.file_stats:
        all_classes.extend([size for _, size in fs.classes])
    
    if all_classes:
        print(f"\nCLASS STATISTICS:")
        print(f"  Largest class:      {max(all_classes):,} lines")
        print(f"  Smallest class:     {min(all_classes):,} lines")
        print(f"  Median class size:  {statistics.median(all_classes):,.0f} lines")
        print(f"  Average class size: {statistics.mean(all_classes):,.1f} lines")
    
    # Function statistics
    all_functions = []
    for fs in stats.file_stats:
        all_functions.extend([size for _, size in fs.functions])
    
    if all_functions:
        print(f"\nFUNCTION STATISTICS:")
        print(f"  Largest function:      {max(all_functions):,} lines")
        print(f"  Smallest function:     {min(all_functions):,} lines")
        print(f"  Median function size:  {statistics.median(all_functions):,.0f} lines")
        print(f"  Average function size: {statistics.mean(all_functions):,.1f} lines")
    
    # Top files by size
    top_files = sorted(stats.file_stats, key=lambda x: x.total_lines, reverse=True)[:10]
    print(f"\nTOP 10 LARGEST FILES:")
    for i, fs in enumerate(top_files, 1):
        print(f"  {i:2d}. {fs.path:40} {fs.total_lines:4d} lines")
    
    # Top classes by size
    all_classes_with_file = []
    for fs in stats.file_stats:
        for class_name, size in fs.classes:
            all_classes_with_file.append((class_name, size, fs.path))
    
    if all_classes_with_file:
        top_classes = sorted(all_classes_with_file, key=lambda x: x[1], reverse=True)[:10]
        print(f"\nTOP 10 LARGEST CLASSES:")
        for i, (name, size, path) in enumerate(top_classes, 1):
            print(f"  {i:2d}. {name:25} {size:4d} lines ({path})")
    
    # Top functions by size
    all_functions_with_file = []
    for fs in stats.file_stats:
        for func_name, size in fs.functions:
            all_functions_with_file.append((func_name, size, fs.path))
    
    if all_functions_with_file:
        top_functions = sorted(all_functions_with_file, key=lambda x: x[1], reverse=True)[:10]
        print(f"\nTOP 10 LARGEST FUNCTIONS:")
        for i, (name, size, path) in enumerate(top_functions, 1):
            print(f"  {i:2d}. {name:25} {size:4d} lines ({path})")


def main():
    """Main entry point."""
    # Analyze the src directory
    analyzer = CodeAnalyzer("src")
    stats = analyzer.analyze_directory()
    print_statistics(stats)
    
    # Also include the CLI files in the root
    print("\n" + "=" * 60)
    print("INCLUDING ROOT CLI FILES")
    print("=" * 60)
    
    root_analyzer = CodeAnalyzer(".")
    root_files = ["bmlibrarian_cli.py", "bmlibrarian_cli_refactored.py"]
    
    for filename in root_files:
        file_path = Path(filename)
        if file_path.exists():
            try:
                file_stat = root_analyzer.analyze_file(file_path)
                stats.file_stats.append(file_stat)
                stats.total_files += 1
                stats.total_lines += file_stat.total_lines
                stats.total_code_lines += file_stat.code_lines
                stats.total_comment_lines += file_stat.comment_lines
                stats.total_blank_lines += file_stat.blank_lines
                stats.total_classes += len(file_stat.classes)
                stats.total_functions += len(file_stat.functions)
                print(f"Added {filename}: {file_stat.total_lines} lines")
            except Exception as e:
                print(f"Warning: Could not analyze {filename}: {e}")
    
    print(f"\nFINAL TOTALS INCLUDING ROOT FILES:")
    print(f"  Total files:        {stats.total_files:,}")
    print(f"  Total lines:        {stats.total_lines:,}")
    print(f"  Code lines:         {stats.total_code_lines:,}")
    print(f"  Comment lines:      {stats.total_comment_lines:,}")
    print(f"  Blank lines:        {stats.total_blank_lines:,}")


if __name__ == "__main__":
    main()