"""
Constants for Study Assessment Lab Qt Plugin.

Centralizes all color definitions, thresholds, and magic numbers
for consistent styling and easy maintenance.
"""

# Quality score colors
QUALITY_COLORS = {
    'excellent': '#2E7D32',      # Green 800
    'good': '#43A047',           # Green 600
    'fair': '#F57C00',           # Orange 600
    'poor': '#E64A19',           # Deep Orange 600
    'very_poor': '#C62828'       # Red 800
}

# Confidence level colors
CONFIDENCE_COLORS = {
    'high': '#2E7D32',           # Green 800
    'medium': '#1976D2',         # Blue 700
    'low': '#F57C00',            # Orange 600
    'very_low': '#C62828'        # Red 800
}

# Bias risk colors
BIAS_RISK_COLORS = {
    'low': '#2E7D32',            # Green 800
    'moderate': '#F57C00',       # Orange 600
    'high': '#C62828',           # Red 800
    'unclear': '#757575'         # Grey 600
}

# Section background colors
SECTION_COLORS = {
    'classification_bg': '#E3F2FD',  # Blue 50
    'quality_bg': '#FFF3E0',         # Orange 50
    'design_bg': '#F3E5F5',          # Purple 50
    'design_text': '#6A1B9A',        # Purple 800
    'strengths_bg': '#E8F5E9',       # Green 50
    'limitations_bg': '#FFEBEE',     # Red 50
    'bias_bg': '#E8EAF6',            # Indigo 50
    'title': '#1976D2',              # Blue 700
    'info': '#1976D2',               # Blue 700
    'success': '#2E7D32',            # Green 800
    'error': '#C62828'               # Red 800
}

# Quality score thresholds
QUALITY_THRESHOLDS = {
    'excellent': 9.0,
    'good': 7.0,
    'fair': 5.0,
    'poor': 3.0
}

# Confidence thresholds
CONFIDENCE_THRESHOLDS = {
    'high': 0.8,
    'medium': 0.6,
    'low': 0.4
}

# UI sizing constants
UI_SIZES = {
    'model_combo_width': 300,
    'doc_id_input_width': 200,
    'button_height': 35,
    'load_button_width': 150,
    'clear_button_width': 80,
    'refresh_button_width': 80,
    'bias_type_width': 120,
    'bias_badge_width': 100,
    'info_label_width': 120
}

# Splitter initial sizes
SPLITTER_SIZES = {
    'document_panel': 400,
    'assessment_panel': 600
}
