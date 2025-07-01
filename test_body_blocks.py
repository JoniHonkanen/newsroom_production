#!/usr/bin/env python
# File: test_body_blocks.py

import json
import sys
import re
import markdown
from typing import Dict, Any, List, Optional

class MockNewsArticleService:
    """A simplified version of NewsArticleService for testing only."""
    
    def convert_markdown_to_html_blocks(self, markdown_text: str) -> List[Dict[str, Any]]:
        """
        Convert markdown text to a list of standardized content blocks.
        """
        # First, we need to split the markdown into logical blocks
        # by parsing the markdown text directly
        markdown_blocks = []
        
        # Process the markdown by line to identify different types of content
        lines = markdown_text.split('\n')
        current_block_type = None
        current_block_content = []
        current_block_markdown = []
        block_count = 0
        
        # Helper function to add the current block to our list
        def add_current_block():
            nonlocal current_block_type, current_block_content, current_block_markdown, block_count
            
            if not current_block_content:
                return
                
            block_count += 1
            markdown_content = '\n'.join(current_block_markdown)
            text_content = '\n'.join(current_block_content)
            
            # Convert just this block to HTML
            html_content = markdown.markdown(markdown_content, extensions=["tables", "fenced_code"])
            
            # Create the block with standard fields
            block = {
                "order": block_count,
                "type": current_block_type,
                "content": text_content,
                "markdown": markdown_content,
                "html": html_content
            }
            
            # Add additional fields based on type
            if current_block_type == "image":
                # Try to extract src and alt from markdown image syntax: ![alt](url)
                img_match = re.search(r'!\[(.*?)\]\((.*?)\)', markdown_content)
                if img_match:
                    alt_text = img_match.group(1)
                    img_url = img_match.group(2)
                    block["content"] = img_url
                    block["alt"] = alt_text
            
            # Special handling for lists
            if current_block_type == "list":
                # Extract list items
                list_items = []
                for line in current_block_content:
                    item_match = re.search(r'^[-*] (.+)$|^\d+\. (.+)$', line.strip())
                    if item_match:
                        item_text = item_match.group(1) if item_match.group(1) else item_match.group(2)
                        list_items.append(item_text)
                block["items"] = list_items
            
            markdown_blocks.append(block)
            current_block_content = []
            current_block_markdown = []
            current_block_type = None
        
        # First line is usually the headline
        if lines and lines[0].startswith('# '):
            current_block_type = "headline"
            current_block_content = [lines[0][2:].strip()]
            current_block_markdown = [lines[0]]
            add_current_block()
            lines = lines[1:]
        
        # Process the rest of the content
        for i, line in enumerate(lines):
            # Skip empty lines between blocks
            if not line.strip() and not current_block_content:
                continue
                
            # Detect headers
            if line.startswith('# '):
                add_current_block()
                current_block_type = "headline"
                current_block_content = [line[2:].strip()]
                current_block_markdown = [line]
            elif line.startswith('## '):
                add_current_block()
                current_block_type = "subheading"
                current_block_content = [line[3:].strip()]
                current_block_markdown = [line]
            # Detect images: ![alt](url)
            elif re.match(r'!\[.*?\]\(.*?\)', line):
                add_current_block()
                current_block_type = "image"
                current_block_content = [line]
                current_block_markdown = [line]
            # Detect blockquotes
            elif line.startswith('> '):
                if current_block_type != "quote":
                    add_current_block()
                    current_block_type = "quote"
                current_block_content.append(line[2:].strip())
                current_block_markdown.append(line)
            # Detect lists
            elif re.match(r'^[-*] |^\d+\. ', line):
                if current_block_type != "list":
                    add_current_block()
                    current_block_type = "list"
                current_block_content.append(line)
                current_block_markdown.append(line)
            # Everything else is paragraph text
            else:
                # Detect paragraph breaks (empty lines)
                if not line.strip() and current_block_content:
                    add_current_block()
                else:
                    # Handle intro paragraph (first text paragraph)
                    if not current_block_type and block_count < 2:
                        current_block_type = "intro"
                    elif not current_block_type:
                        current_block_type = "text"
                    
                    if line.strip():  # Only add non-empty lines
                        current_block_content.append(line.strip())
                        current_block_markdown.append(line)
        
        # Add the final block if there's content
        add_current_block()
        
        # Return the blocks
        return markdown_blocks


def test_body_blocks():
    """Test the body_blocks generation functionality."""
    
    # Create instance of the mock service
    service = MockNewsArticleService()
    
    # Test markdown content
    test_markdown = """# Finland's AI Strategy Expands with New Investments

Finland is strengthening its position as a leader in artificial intelligence through increased funding and education initiatives. The government has announced plans to invest heavily in AI research and education.

## New Research Centers

The Finnish government is establishing three new AI research centers in Helsinki, Tampere, and Oulu. These centers will focus on developing ethical AI applications for healthcare, education, and environmental monitoring.

![AI Research Lab](https://example.com/ai-lab.jpg)

* Helsinki center will focus on healthcare applications
* Tampere center will develop educational AI tools
* Oulu center will concentrate on environmental monitoring

> "Finland aims to be among the top five countries in AI research by 2030," said the Minister of Education and Science.

The initiative includes a €100 million investment over the next five years.
"""
    
    # Generate body blocks
    body_blocks = service.convert_markdown_to_html_blocks(test_markdown)
    
    # Print the results
    print("Generated body blocks:")
    print(json.dumps(body_blocks, indent=2))
    
    # Validate the structure
    print("\nValidating structure:")
    validate_blocks(body_blocks)
    
def validate_blocks(blocks: List[Dict[str, Any]]):
    """Validate the structure of the content blocks."""
    required_fields = ["order", "type", "content"]
    block_types = set()
    
    for i, block in enumerate(blocks):
        # Check for required fields
        for field in required_fields:
            if field not in block:
                print(f"Block {i+1} missing required field: {field}")
        
        # Check order sequence
        if block.get("order") != i + 1:
            print(f"Block {i+1} has incorrect order value: {block.get('order')}")
        
        # Collect block types
        block_types.add(block.get("type", "unknown"))
        
    print(f"Found block types: {', '.join(sorted(block_types))}")
    print(f"Total blocks: {len(blocks)}")

if __name__ == "__main__":
    test_body_blocks()
