#!/usr/bin/env python3
import sys
import yaml
import argparse
from typing import Any, Dict, List, Union

def recursive_sort(data: Any) -> Any:
    """
    Recursively sort all dictionaries by key and lists by value.
    
    Args:
        data: The data structure to sort (can be a dict, list, or any other type)
        
    Returns:
        The sorted data structure
    """
    if isinstance(data, dict):
        # Sort the dictionary by keys
        return {key: recursive_sort(data[key]) for key in sorted(data.keys())}
    elif isinstance(data, list):
        # Attempt to sort the list
        try:
            # First recursively sort any dicts/lists in the list
            sorted_items = [recursive_sort(item) for item in data]
            # Then try to sort the list itself
            # This will fail if items aren't comparable
            return sorted(sorted_items)
        except TypeError:
            # If items aren't comparable, return the list with recursively sorted elements
            return [recursive_sort(item) for item in data]
    else:
        # If it's not a dict or list, return as is
        return data

def document_sort_key(doc):
    """
    Create a sort key for documents. This is a heuristic approach:
    - For dicts, use the sorted tuple of string representations of (key, value) pairs
    - For lists, use the string representation of the sorted list
    - For other types, use the string representation
    
    This won't produce perfect sorting in all cases but aims to be stable and sensible.
    """
    try:
        if isinstance(doc, dict):
            # Sort by a string representation of all key-value pairs
            if doc:
                return str(sorted((str(k), str(v)) for k, v in doc.items()))
            else:
                return "{}"  # Empty dict
        elif isinstance(doc, list):
            # Sort by a string representation of the list
            if doc:
                return str(sorted(str(x) for x in doc))
            else:
                return "[]"  # Empty list
        else:
            return str(doc)
    except:
        # Fallback to string representation if comparison fails
        return str(doc)

def main():
    parser = argparse.ArgumentParser(description='Recursively sort YAML data')
    parser.add_argument('file', nargs='?', type=argparse.FileType('r'), 
                        default=sys.stdin, help='YAML file (default: stdin)')
    parser.add_argument('-o', '--output', type=argparse.FileType('w'),
                        default=sys.stdout, help='Output file (default: stdout)')
    parser.add_argument('--indent', type=int, default=2,
                        help='Indentation spaces for output YAML (default: 2)')
    parser.add_argument('--no-sort-docs', action='store_true',
                        help='Don\'t sort documents, only sort within documents')
    
    args = parser.parse_args()
    
    try:
        # Load all YAML documents from file or stdin
        yaml_content = args.file.read()
        
        # Process each document
        documents = list(yaml.safe_load_all(yaml_content))
        
        # Sort each document's content
        sorted_documents = [recursive_sort(doc) for doc in documents]
        
        # Sort the documents themselves if requested
        if not args.no_sort_docs and len(documents) > 1:
            try:
                sorted_documents.sort(key=document_sort_key)
            except Exception as e:
                print(f"Warning: Could not sort documents: {e}", file=sys.stderr)
        
        # Output sorted documents
        yaml.dump_all(sorted_documents, args.output, sort_keys=False, 
                     indent=args.indent, explicit_start=True)
        
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {e}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"I/O error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()