from __future__ import annotations

import re


def parse_policy_markdown(markdown_text: str) -> list[dict]:
    """Parse markdown into chunks based on H2 and H3 structure."""
    chunks = []
    
    # Split by H2
    h2_sections = re.split(r'\n##\s+', markdown_text)
    
    # The first section is before the first H2 (typically H1 and intro)
    # We can skip or include it. Let's include if it has useful content.
    
    for h2_section in h2_sections:
        lines = h2_section.strip().split('\n')
        if not lines:
            continue
            
        h2_title = lines[0].strip()
        h2_content = '\n'.join(lines[1:])
        
        # Split by H3 within H2
        h3_sections = re.split(r'\n###\s+', h2_content)
        
        # If there are no H3s, create a single chunk for the H2
        if len(h3_sections) <= 1:
            # Check if there's actual content
            content = h3_sections[0].strip()
            if content:
                chunks.append({
                    "section_h2": h2_title,
                    "section_h3": "",
                    "citation": h2_title,
                    "rendered_text": f"## {h2_title}\n\n{content}"
                })
        else:
            # h3_sections[0] is the part of H2 before any H3
            intro_to_h2 = h3_sections[0].strip()
            
            for h3_part in h3_sections[1:]:
                h3_lines = h3_part.strip().split('\n')
                if not h3_lines:
                    continue
                
                h3_title = h3_lines[0].strip()
                h3_body = '\n'.join(h3_lines[1:]).strip()
                
                citation = f"{h2_title} > {h3_title}"
                rendered_text = f"## {h2_title}\n"
                if intro_to_h2:
                    rendered_text += f"{intro_to_h2}\n\n"
                rendered_text += f"### {h3_title}\n\n{h3_body}"
                
                chunks.append({
                    "section_h2": h2_title,
                    "section_h3": h3_title,
                    "citation": citation,
                    "rendered_text": rendered_text
                })
                
    return chunks
