#!/usr/bin/env python3
"""
Ollama Model Transfer Helper

This module provides functionality to transfer Ollama models between computers
by packaging manifest files and their associated blobs into ZIP archives.

Ollama stores models in ~/.ollama/models/ with:
- manifests/: Contains model manifest files organized by registry/namespace/model/tag
- blobs/: Contains binary data files referenced by SHA256 digests

Usage:
    python ollama_transfer.py export <model_name> <output_file>
    python ollama_transfer.py import <zip_file>
    python ollama_transfer.py list
"""

import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Set, Tuple
import argparse
import sys


class OllamaTransfer:
    """Helper class for transferring Ollama models between systems."""
    
    def __init__(self, ollama_path: str = None):
        """Initialize with Ollama installation path."""
        self.ollama_path = Path(ollama_path or os.path.expanduser("~/.ollama"))
        self.models_path = self.ollama_path / "models"
        self.manifests_path = self.models_path / "manifests"
        self.blobs_path = self.models_path / "blobs"
    
    def _validate_ollama_installation(self) -> bool:
        """Check if Ollama installation exists and is valid."""
        required_dirs = [self.models_path, self.manifests_path, self.blobs_path]
        return all(path.exists() and path.is_dir() for path in required_dirs)
    
    def list_models(self) -> List[str]:
        """List all available models in the Ollama installation."""
        if not self._validate_ollama_installation():
            raise RuntimeError(f"Invalid Ollama installation at {self.ollama_path}")
        
        models = []
        for root, dirs, files in os.walk(self.manifests_path):
            # Skip .DS_Store and other hidden files
            for file in files:
                if not file.startswith('.'):
                    # Convert path to model name format
                    rel_path = os.path.relpath(os.path.join(root, file), self.manifests_path)
                    # Convert path separators to model name format
                    model_name = rel_path.replace(os.sep, '/')
                    models.append(model_name)
        
        return sorted(models)
    
    def resolve_model_name(self, model_input: str) -> str:
        """
        Resolve a model name input to the full manifest path.
        
        Supports various input formats:
        - Full path: registry.ollama.ai/library/model/tag
        - Short name: model:tag or model/tag
        - Just model name: model (will find latest or first available)
        
        Args:
            model_input: Model identifier in various formats
            
        Returns:
            Full model path that exists in manifests
            
        Raises:
            FileNotFoundError: If no matching model is found
        """
        if not self._validate_ollama_installation():
            raise RuntimeError(f"Invalid Ollama installation at {self.ollama_path}")
        
        # Get all available models
        all_models = self.list_models()
        
        # Try exact match first
        if model_input in all_models:
            return model_input
        
        # Try case-insensitive exact match
        for model in all_models:
            if model.lower() == model_input.lower():
                return model
        
        # Extract base name for pattern matching
        input_clean = model_input.replace(':', '/')
        input_parts = input_clean.split('/')
        
        # Find models that match the pattern
        matches = []
        for model in all_models:
            model_parts = model.split('/')
            
            # Check if all input parts are contained in the model path
            match_found = True
            for part in input_parts:
                if not any(part.lower() in model_part.lower() for model_part in model_parts):
                    match_found = False
                    break
            
            if match_found:
                matches.append(model)
        
        # If no matches found, try substring matching
        if not matches:
            for model in all_models:
                if all(part.lower() in model.lower() for part in input_parts):
                    matches.append(model)
        
        if not matches:
            # Show available models that might be similar
            similar = [m for m in all_models if any(part.lower() in m.lower() for part in input_parts)]
            if similar:
                similar_str = '\n  '.join(similar[:10])  # Show first 10
                raise FileNotFoundError(
                    f"Model '{model_input}' not found. Similar models:\n  {similar_str}"
                )
            else:
                raise FileNotFoundError(f"Model '{model_input}' not found.")
        
        # If multiple matches, prefer ones with 'latest' tag, then shortest path
        if len(matches) > 1:
            latest_matches = [m for m in matches if m.endswith('/latest')]
            if latest_matches:
                matches = latest_matches
            
            # Sort by path length (shorter is more likely to be what user wants)
            matches.sort(key=len)
            
            print(f"Multiple matches found for '{model_input}', using: {matches[0]}")
            if len(matches) > 1:
                print(f"Other matches: {', '.join(matches[1:5])}")  # Show first 4 others
        
        return matches[0]
    
    def _parse_manifest(self, manifest_path: Path) -> Dict:
        """Parse a manifest file and return its contents."""
        try:
            with open(manifest_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            raise RuntimeError(f"Failed to parse manifest {manifest_path}: {e}")
    
    def _extract_blob_digests(self, manifest: Dict) -> Set[str]:
        """Extract all blob digests referenced in a manifest."""
        digests = set()
        
        # Add config digest
        if 'config' in manifest and 'digest' in manifest['config']:
            digests.add(manifest['config']['digest'])
        
        # Add layer digests
        if 'layers' in manifest:
            for layer in manifest['layers']:
                if 'digest' in layer:
                    digests.add(layer['digest'])
        
        return digests
    
    def _digest_to_filename(self, digest: str) -> str:
        """Convert a digest to blob filename format."""
        # Remove 'sha256:' prefix and use full hash as filename
        return digest.replace('sha256:', 'sha256-')
    
    def export_model(self, model_name: str, output_file: str) -> bool:
        """
        Export a model to a ZIP file.
        
        Args:
            model_name: Model identifier (supports short names like 'medgemma:latest')
            output_file: Output ZIP file path
            
        Returns:
            True if successful, False otherwise
        """
        if not self._validate_ollama_installation():
            raise RuntimeError(f"Invalid Ollama installation at {self.ollama_path}")
        
        # Resolve model name to full path
        resolved_model_name = self.resolve_model_name(model_name)
        print(f"Resolved model name: {resolved_model_name}")
        
        # Find manifest file
        manifest_path = self.manifests_path / resolved_model_name
        if not manifest_path.exists():
            raise FileNotFoundError(f"Model manifest not found: {manifest_path}")
        
        # Parse manifest to get blob references
        manifest = self._parse_manifest(manifest_path)
        blob_digests = self._extract_blob_digests(manifest)
        
        # Verify all blobs exist
        missing_blobs = []
        blob_paths = []
        for digest in blob_digests:
            blob_filename = self._digest_to_filename(digest)
            blob_path = self.blobs_path / blob_filename
            if blob_path.exists():
                blob_paths.append((digest, blob_path))
            else:
                missing_blobs.append(digest)
        
        if missing_blobs:
            raise FileNotFoundError(f"Missing blob files: {missing_blobs}")
        
        # Create ZIP archive
        try:
            with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as zipf:
                # Add manifest file
                manifest_arcname = f"manifests/{resolved_model_name}"
                zipf.write(manifest_path, manifest_arcname)
                
                # Add blob files
                for digest, blob_path in blob_paths:
                    blob_filename = self._digest_to_filename(digest)
                    blob_arcname = f"blobs/{blob_filename}"
                    print(f"Adding blob: {blob_filename} ({blob_path.stat().st_size:,} bytes)")
                    zipf.write(blob_path, blob_arcname)
                
                # Add metadata
                metadata = {
                    "model_name": resolved_model_name,
                    "original_input": model_name,
                    "manifest_path": manifest_arcname,
                    "blob_count": len(blob_paths),
                    "total_blobs": len(blob_digests),
                    "export_version": "1.0"
                }
                zipf.writestr("metadata.json", json.dumps(metadata, indent=2))
            
            print(f"Successfully exported model '{resolved_model_name}' to '{output_file}'")
            print(f"Archive contains: 1 manifest + {len(blob_paths)} blobs")
            return True
            
        except Exception as e:
            raise RuntimeError(f"Failed to create ZIP archive: {e}")
    
    def import_model(self, zip_file: str, force: bool = False) -> bool:
        """
        Import a model from a ZIP file.
        
        Args:
            zip_file: Input ZIP file path
            force: Overwrite existing files if True
            
        Returns:
            True if successful, False otherwise
        """
        if not self._validate_ollama_installation():
            raise RuntimeError(f"Invalid Ollama installation at {self.ollama_path}")
        
        if not os.path.exists(zip_file):
            raise FileNotFoundError(f"ZIP file not found: {zip_file}")
        
        try:
            with zipfile.ZipFile(zip_file, 'r') as zipf:
                # Read metadata
                try:
                    metadata_content = zipf.read("metadata.json")
                    metadata = json.loads(metadata_content)
                    model_name = metadata.get("model_name")
                    print(f"Importing model: {model_name}")
                except KeyError:
                    raise RuntimeError("Invalid ZIP file: missing metadata.json")
                
                # Check if model already exists
                target_manifest = self.manifests_path / model_name
                if target_manifest.exists() and not force:
                    raise FileExistsError(f"Model already exists: {model_name}. Use --force to overwrite.")
                
                # Extract files
                for member in zipf.infolist():
                    if member.filename == "metadata.json":
                        continue
                    
                    # Determine target path
                    if member.filename.startswith("manifests/"):
                        rel_path = member.filename[10:]  # Remove "manifests/" prefix
                        target_path = self.manifests_path / rel_path
                    elif member.filename.startswith("blobs/"):
                        rel_path = member.filename[6:]  # Remove "blobs/" prefix
                        target_path = self.blobs_path / rel_path
                    else:
                        print(f"Warning: Skipping unknown file: {member.filename}")
                        continue
                    
                    # Create parent directories if needed
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Extract file
                    if target_path.exists() and not force:
                        print(f"Skipping existing file: {target_path}")
                        continue
                    
                    print(f"Extracting: {member.filename} -> {target_path}")
                    with zipf.open(member) as src, open(target_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                
                print(f"Successfully imported model '{model_name}'")
                return True
                
        except Exception as e:
            raise RuntimeError(f"Failed to import model: {e}")
    
    def get_model_info(self, model_name: str) -> Dict:
        """Get detailed information about a model."""
        # Resolve model name to full path
        resolved_model_name = self.resolve_model_name(model_name)
        
        manifest_path = self.manifests_path / resolved_model_name
        if not manifest_path.exists():
            raise FileNotFoundError(f"Model not found: {resolved_model_name}")
        
        manifest = self._parse_manifest(manifest_path)
        blob_digests = self._extract_blob_digests(manifest)
        
        # Calculate sizes
        total_size = 0
        blob_info = []
        for digest in blob_digests:
            blob_filename = self._digest_to_filename(digest)
            blob_path = self.blobs_path / blob_filename
            if blob_path.exists():
                size = blob_path.stat().st_size
                total_size += size
                blob_info.append({
                    "digest": digest,
                    "filename": blob_filename,
                    "size": size,
                    "exists": True
                })
            else:
                blob_info.append({
                    "digest": digest,
                    "filename": blob_filename,
                    "size": 0,
                    "exists": False
                })
        
        return {
            "model_name": resolved_model_name,
            "original_input": model_name,
            "manifest_path": str(manifest_path),
            "total_size": total_size,
            "blob_count": len(blob_digests),
            "blobs": blob_info
        }


def format_size(size_bytes: int) -> str:
    """Format size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def main():
    """Command-line interface for Ollama model transfer."""
    parser = argparse.ArgumentParser(
        description="Transfer Ollama models between computers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list
  %(prog)s export registry.ollama.ai/library/llama2/latest llama2.zip
  %(prog)s import llama2.zip
  %(prog)s info registry.ollama.ai/library/llama2/latest
        """
    )
    
    parser.add_argument(
        '--ollama-path',
        help='Path to Ollama installation (default: ~/.ollama)',
        default=None
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available models')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export a model to ZIP file')
    export_parser.add_argument('model_name', help='Model name to export')
    export_parser.add_argument('output_file', help='Output ZIP file path')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import a model from ZIP file')
    import_parser.add_argument('zip_file', help='ZIP file to import')
    import_parser.add_argument('--force', action='store_true', help='Overwrite existing files')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Show model information')
    info_parser.add_argument('model_name', help='Model name to examine')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        transfer = OllamaTransfer(args.ollama_path)
        
        if args.command == 'list':
            models = transfer.list_models()
            if not models:
                print("No models found.")
                return 0
            
            print(f"Found {len(models)} models:")
            for model in models:
                print(f"  {model}")
                
        elif args.command == 'export':
            transfer.export_model(args.model_name, args.output_file)
            
        elif args.command == 'import':
            transfer.import_model(args.zip_file, args.force)
            
        elif args.command == 'info':
            info = transfer.get_model_info(args.model_name)
            print(f"Model: {info['model_name']}")
            print(f"Manifest: {info['manifest_path']}")
            print(f"Total size: {format_size(info['total_size'])}")
            print(f"Blob count: {info['blob_count']}")
            print("\nBlobs:")
            for blob in info['blobs']:
                status = "✓" if blob['exists'] else "✗"
                size_str = format_size(blob['size']) if blob['exists'] else "missing"
                print(f"  {status} {blob['filename']} ({size_str})")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())