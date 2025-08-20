"""
Tests for ReportingAgent

Tests report synthesis, reference formatting, and citation validation.
"""

import json
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from typing import List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bmlibrarian.agents.reporting_agent import ReportingAgent, Reference, Report
from bmlibrarian.agents.citation_agent import Citation


class TestReportingAgent(unittest.TestCase):
    """Test cases for ReportingAgent functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_orchestrator = Mock()
        self.agent = ReportingAgent(
            orchestrator=self.mock_orchestrator,
            ollama_url="http://test:11434",
            model="test-model"
        )
        
        # Sample citations for testing
        self.sample_citations = [
            Citation(
                passage="COVID-19 vaccines show 95% effectiveness in preventing severe disease",
                summary="High vaccine effectiveness demonstrated",
                relevance_score=0.9,
                document_id="12345678",
                document_title="COVID-19 Vaccine Effectiveness Study",
                authors=["Smith, J.", "Johnson, A."],
                publication_date="2023-01-15",
                pmid="37123456"
            ),
            Citation(
                passage="Side effects were mild and occurred in less than 5% of recipients",
                summary="Low rate of adverse effects reported",
                relevance_score=0.85,
                document_id="12345679", 
                document_title="Safety Profile of mRNA Vaccines",
                authors=["Davis, M.", "Wilson, R.", "Garcia, L."],
                publication_date="2023-03-20",
                pmid="37234567"
            ),
            Citation(
                passage="Booster shots maintain immunity levels above 85% after 6 months",
                summary="Sustained immunity with booster vaccination",
                relevance_score=0.8,
                document_id="12345680",
                document_title="Long-term Immunity Study",
                authors=["Brown, K.", "Taylor, S.", "Miller, D.", "Anderson, P.", "White, B.", "Jones, N.", "Lee, H."],
                publication_date="2023-05-10",
                pmid="37345678"
            )
        ]
        
        self.sample_question = "What is the effectiveness and safety of COVID-19 vaccines?"
    
    def test_reference_creation(self):
        """Test creation of numbered references from citations."""
        references = self.agent.create_references(self.sample_citations)
        
        self.assertEqual(len(references), 3)
        self.assertEqual(references[0].number, 1)
        self.assertEqual(references[1].number, 2) 
        self.assertEqual(references[2].number, 3)
        
        # Check reference content
        self.assertEqual(references[0].document_id, "12345678")
        self.assertEqual(references[0].title, "COVID-19 Vaccine Effectiveness Study")
        self.assertEqual(references[0].pmid, "37123456")
    
    def test_reference_deduplication(self):
        """Test that duplicate document IDs create only one reference."""
        # Add duplicate citation with same document ID
        duplicate_citation = Citation(
            passage="Additional finding from same study",
            summary="Extra evidence from same document",
            relevance_score=0.75,
            document_id="12345678",  # Same ID as first citation
            document_title="COVID-19 Vaccine Effectiveness Study",
            authors=["Smith, J.", "Johnson, A."],
            publication_date="2023-01-15",
            pmid="37123456"
        )
        
        citations_with_duplicate = self.sample_citations + [duplicate_citation]
        references = self.agent.create_references(citations_with_duplicate)
        
        # Should still only have 3 references, not 4
        self.assertEqual(len(references), 3)
        
        # Check document IDs are unique
        doc_ids = [ref.document_id for ref in references]
        self.assertEqual(len(doc_ids), len(set(doc_ids)))
    
    def test_vancouver_reference_formatting(self):
        """Test Vancouver-style reference formatting."""
        reference = Reference(
            number=1,
            authors=["Smith, J.", "Johnson, A.", "Brown, K."],
            title="Test Study Title",
            publication_date="2023-01-15",
            document_id="12345678",
            pmid="37123456"
        )
        
        formatted = reference.format_vancouver_style()
        expected = "Smith, J., Johnson, A., Brown, K.. Test Study Title. 2023; PMID: 37123456"
        self.assertEqual(formatted, expected)
    
    def test_vancouver_formatting_many_authors(self):
        """Test Vancouver formatting with >6 authors uses et al."""
        reference = Reference(
            number=1,
            authors=["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"],
            title="Study with Many Authors",
            publication_date="2023-01-01",
            document_id="12345678"
        )
        
        formatted = reference.format_vancouver_style()
        self.assertIn("A1, A2, A3, A4, A5, A6, et al.", formatted)
        self.assertNotIn("A7", formatted)
        self.assertNotIn("A8", formatted)
    
    def test_citation_to_reference_mapping(self):
        """Test mapping citations to reference numbers."""
        references = self.agent.create_references(self.sample_citations)
        doc_to_ref = self.agent.map_citations_to_references(self.sample_citations, references)
        
        self.assertEqual(doc_to_ref["12345678"], 1)
        self.assertEqual(doc_to_ref["12345679"], 2)
        self.assertEqual(doc_to_ref["12345680"], 3)
    
    def test_evidence_strength_assessment(self):
        """Test evidence strength assessment based on citation quality."""
        # Strong evidence: many citations, high relevance
        strong_citations = [
            Citation("passage1", "summary1", 0.9, "doc1", "title1", ["A1"], "2023-01-01"),
            Citation("passage2", "summary2", 0.85, "doc2", "title2", ["A2"], "2023-01-01"),
            Citation("passage3", "summary3", 0.88, "doc3", "title3", ["A3"], "2023-01-01"),
            Citation("passage4", "summary4", 0.9, "doc4", "title4", ["A4"], "2023-01-01"),
            Citation("passage5", "summary5", 0.87, "doc5", "title5", ["A5"], "2023-01-01")
        ]
        
        strength = self.agent.assess_evidence_strength(strong_citations)
        self.assertEqual(strength, "Strong")
        
        # Moderate evidence
        moderate_citations = self.sample_citations  # 3 citations, good relevance
        strength = self.agent.assess_evidence_strength(moderate_citations)
        self.assertEqual(strength, "Moderate")
        
        # Limited evidence: few citations
        limited_citations = self.sample_citations[:2]
        strength = self.agent.assess_evidence_strength(limited_citations)
        self.assertEqual(strength, "Limited")
        
        # Insufficient evidence: no citations
        strength = self.agent.assess_evidence_strength([])
        self.assertEqual(strength, "Insufficient")
    
    @patch('requests.get')
    def test_connection_success(self, mock_get):
        """Test successful connection to Ollama."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = self.agent.test_connection()
        self.assertTrue(result)
        mock_get.assert_called_once_with("http://test:11434/api/tags", timeout=5)
    
    @patch('requests.get')
    def test_connection_failure(self, mock_get):
        """Test failed connection to Ollama."""
        mock_get.side_effect = Exception("Connection error")
        
        result = self.agent.test_connection()
        self.assertFalse(result)
    
    def test_citation_validation_success(self):
        """Test validation of valid citations."""
        valid_citations, errors = self.agent.validate_citations(self.sample_citations)
        
        self.assertEqual(len(valid_citations), 3)
        self.assertEqual(len(errors), 0)
    
    def test_citation_validation_failures(self):
        """Test validation catches invalid citations."""
        invalid_citations = [
            Citation("", "summary", 0.8, "doc1", "title1", ["A1"], "2023-01-01"),  # Empty passage
            Citation("passage", "summary", 0.8, "", "title2", ["A2"], "2023-01-01"),  # Empty doc ID
            Citation("passage", "summary", 0.8, "doc3", "", ["A3"], "2023-01-01"),  # Empty title
            Citation("passage", "summary", 1.5, "doc4", "title4", ["A4"], "2023-01-01"),  # Invalid score
        ]
        
        valid_citations, errors = self.agent.validate_citations(invalid_citations)
        
        self.assertEqual(len(valid_citations), 0)
        self.assertEqual(len(errors), 4)
        self.assertIn("Empty passage", errors[0])
        self.assertIn("Missing document ID", errors[1])
        self.assertIn("Missing document title", errors[2])
        self.assertIn("Invalid relevance score", errors[3])
    
    @patch('requests.post')
    @patch('requests.get')
    def test_synthesize_report_success(self, mock_get, mock_post):
        """Test successful report synthesis."""
        # Mock connection test
        mock_get.return_value.status_code = 200
        
        # Mock Ollama response
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {
            'response': json.dumps({
                'synthesized_answer': 'COVID-19 vaccines demonstrate high effectiveness (95%) in preventing severe disease [1]. Safety profiles show mild side effects in less than 5% of recipients [2]. Booster shots maintain immunity levels above 85% after 6 months [3]. These findings support the continued use of vaccination programs for pandemic control.',
                'methodology_note': 'Synthesis based on 3 high-quality citations from peer-reviewed studies with relevance scores ≥0.8.'
            })
        }
        mock_post.return_value = mock_post_response
        
        report = self.agent.synthesize_report(self.sample_question, self.sample_citations)
        
        self.assertIsNotNone(report)
        self.assertIsInstance(report, Report)
        self.assertEqual(report.user_question, self.sample_question)
        self.assertIn("95%", report.synthesized_answer)
        self.assertIn("[1]", report.synthesized_answer)  # Check citations included
        self.assertEqual(len(report.references), 3)
        self.assertEqual(report.citation_count, 3)
        self.assertEqual(report.unique_documents, 3)
        self.assertEqual(report.evidence_strength, "Moderate")
    
    def test_synthesize_report_insufficient_citations(self):
        """Test report synthesis with insufficient citations."""
        single_citation = [self.sample_citations[0]]
        
        report = self.agent.synthesize_report(
            self.sample_question, 
            single_citation, 
            min_citations=2
        )
        
        self.assertIsNone(report)
    
    @patch('requests.get')
    def test_synthesize_report_no_connection(self, mock_get):
        """Test report synthesis without Ollama connection."""
        mock_get.side_effect = Exception("Connection failed")
        
        report = self.agent.synthesize_report(self.sample_question, self.sample_citations)
        self.assertIsNone(report)
    
    def test_format_report_output(self):
        """Test formatting of report for display."""
        # Create a sample report
        references = self.agent.create_references(self.sample_citations)
        report = Report(
            user_question=self.sample_question,
            synthesized_answer="COVID-19 vaccines show excellent effectiveness [1] with minimal side effects [2]. Boosters maintain immunity [3].",
            references=references,
            evidence_strength="Moderate",
            methodology_note="Based on 3 high-quality peer-reviewed studies.",
            created_at=datetime(2023, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
            citation_count=3,
            unique_documents=3
        )
        
        formatted = self.agent.format_report_output(report)
        
        # Check key components are present
        self.assertIn("Research Question:", formatted)
        self.assertIn(self.sample_question, formatted)
        self.assertIn("Evidence Strength: Moderate", formatted)
        self.assertIn("COVID-19 vaccines show excellent", formatted)
        self.assertIn("REFERENCES", formatted)
        self.assertIn("1. Smith, J., Johnson, A..", formatted)
        self.assertIn("2. Davis, M., Wilson, R., Garcia, L..", formatted)
        self.assertIn("3. Brown, K., Taylor, S., Miller, D., Anderson, P., White, B., Jones, N., et al..", formatted)
        self.assertIn("METHODOLOGY", formatted)
        self.assertIn("Based on 3 high-quality", formatted)
        self.assertIn("REPORT METADATA", formatted)
        self.assertIn("Generated: 2023-06-15 12:00:00 UTC", formatted)
        self.assertIn("Citations analyzed: 3", formatted)
    
    @patch('requests.post')
    @patch('requests.get')
    def test_generate_citation_based_report(self, mock_get, mock_post):
        """Test complete report generation workflow."""
        # Mock successful connection and synthesis
        mock_get.return_value.status_code = 200
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {
            'response': json.dumps({
                'synthesized_answer': 'Test synthesis with citations [1][2][3].',
                'methodology_note': 'Test methodology note.'
            })
        }
        mock_post.return_value = mock_post_response
        
        # Test formatted output
        result = self.agent.generate_citation_based_report(
            self.sample_question, 
            self.sample_citations,
            format_output=True
        )
        
        self.assertIsNotNone(result)
        self.assertIn("Research Question:", result)
        self.assertIn("REFERENCES", result)
        
        # Test unformatted output
        result_unformatted = self.agent.generate_citation_based_report(
            self.sample_question,
            self.sample_citations, 
            format_output=False
        )
        
        self.assertIsNotNone(result_unformatted)
        self.assertEqual(result_unformatted, "Test synthesis with citations [1][2][3].")
        self.assertNotIn("Research Question:", result_unformatted)


class TestReportingAgentIntegration(unittest.TestCase):
    """Test reporting agent integration scenarios."""
    
    def setUp(self):
        """Set up integration test fixtures."""
        self.mock_orchestrator = Mock()
        self.agent = ReportingAgent(orchestrator=self.mock_orchestrator)
    
    def test_full_citation_to_report_workflow(self):
        """Test complete workflow from citations to formatted report."""
        # Sample citations from realistic citation extraction
        citations = [
            Citation(
                passage="Meta-analysis of 15 studies showed aspirin reduces cardiovascular events by 22% (95% CI: 18-26%)",
                summary="Strong evidence for cardiovascular protection from aspirin",
                relevance_score=0.92,
                document_id="98765001", 
                document_title="Aspirin for Primary Prevention of Cardiovascular Disease: Meta-Analysis",
                authors=["Johnson, M.", "Smith, R.", "Davis, L."],
                publication_date="2023-04-15",
                pmid="37654321"
            ),
            Citation(
                passage="Major bleeding events occurred in 0.3% of aspirin users vs 0.2% of controls (RR 1.5, 95% CI 1.2-1.9)",
                summary="Small but significant increase in bleeding risk with aspirin use",
                relevance_score=0.89,
                document_id="98765002",
                document_title="Bleeding Risks Associated with Low-Dose Aspirin: Systematic Review",
                authors=["Taylor, K.", "Brown, P.", "Wilson, J.", "Garcia, M.", "Anderson, S.", "White, T.", "Lee, C."],
                publication_date="2023-02-28", 
                pmid="37543210"
            ),
            Citation(
                passage="Net clinical benefit favors aspirin use in patients with 10-year cardiovascular risk >10%",
                summary="Risk-benefit analysis supports aspirin use in higher-risk patients",
                relevance_score=0.87,
                document_id="98765003",
                document_title="Risk-Benefit Assessment of Aspirin for Primary Prevention",
                authors=["Miller, A.", "Thompson, D."],
                publication_date="2023-01-10",
                pmid="37432109"
            )
        ]
        
        # Test reference creation
        references = self.agent.create_references(citations)
        self.assertEqual(len(references), 3)
        
        # Test Vancouver formatting
        ref1_formatted = references[0].format_vancouver_style()
        self.assertIn("Johnson, M., Smith, R., Davis, L.", ref1_formatted)
        self.assertIn("Meta-Analysis", ref1_formatted)
        self.assertIn("2023", ref1_formatted)
        self.assertIn("PMID: 37654321", ref1_formatted)
        
        ref2_formatted = references[1].format_vancouver_style()
        self.assertIn("Taylor, K., Brown, P., Wilson, J., Garcia, M., Anderson, S., White, T., et al.", ref2_formatted)
        
        # Test evidence strength assessment
        strength = self.agent.assess_evidence_strength(citations)
        self.assertEqual(strength, "Moderate")  # 3 citations, high relevance
        
        # Test citation validation
        valid_citations, errors = self.agent.validate_citations(citations)
        self.assertEqual(len(valid_citations), 3)
        self.assertEqual(len(errors), 0)


if __name__ == '__main__':
    unittest.main()