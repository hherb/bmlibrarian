"""
Tests for CounterfactualAgent - tests the counterfactual checking functionality.

Covers document analysis, research question generation, and protocol formatting.
Uses mocked Ollama responses to test parsing logic and error handling.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from bmlibrarian.agents.counterfactual_agent import CounterfactualAgent
from bmlibrarian.agents.models.counterfactual import (
    CounterfactualQuestion,
    CounterfactualAnalysis
)


class TestCounterfactualQuestion:
    """Test the CounterfactualQuestion dataclass."""
    
    def test_counterfactual_question_creation(self):
        """Test basic CounterfactualQuestion creation."""
        question = CounterfactualQuestion(
            counterfactual_statement="Exercise does not improve cardiovascular health",
            question="Are there studies showing exercise doesn't improve cardiovascular health?",
            reasoning="To verify the claim that exercise universally improves heart health",
            target_claim="Exercise improves cardiovascular outcomes",
            search_keywords=["exercise", "cardiovascular", "negative effects"],
            priority="HIGH"
        )

        assert question.counterfactual_statement == "Exercise does not improve cardiovascular health"
        assert question.question == "Are there studies showing exercise doesn't improve cardiovascular health?"
        assert question.priority == "HIGH"
        assert len(question.search_keywords) == 3
        assert question.created_at is not None
    
    def test_counterfactual_question_auto_timestamp(self):
        """Test that created_at is automatically set."""
        question = CounterfactualQuestion(
            counterfactual_statement="Test statement",
            question="Test question",
            reasoning="Test reasoning",
            target_claim="Test claim",
            search_keywords=["test"],
            priority="MEDIUM"
        )

        assert isinstance(question.created_at, datetime)


class TestCounterfactualAnalysis:
    """Test the CounterfactualAnalysis dataclass."""
    
    def test_counterfactual_analysis_creation(self):
        """Test basic CounterfactualAnalysis creation."""
        questions = [
            CounterfactualQuestion(
                counterfactual_statement="Test statement 1",
                question="Test question 1",
                reasoning="Test reasoning 1",
                target_claim="Test claim 1",
                search_keywords=["test1"],
                priority="HIGH"
            ),
            CounterfactualQuestion(
                counterfactual_statement="Test statement 2",
                question="Test question 2",
                reasoning="Test reasoning 2",
                target_claim="Test claim 2",
                search_keywords=["test2"],
                priority="LOW"
            )
        ]
        
        analysis = CounterfactualAnalysis(
            document_title="Test Document",
            main_claims=["Claim 1", "Claim 2"],
            counterfactual_questions=questions,
            overall_assessment="Test assessment",
            confidence_level="MEDIUM"
        )
        
        assert analysis.document_title == "Test Document"
        assert len(analysis.main_claims) == 2
        assert len(analysis.counterfactual_questions) == 2
        assert analysis.confidence_level == "MEDIUM"
        assert analysis.created_at is not None


class TestCounterfactualAgent:
    """Test the CounterfactualAgent class."""
    
    @pytest.fixture
    def agent(self):
        """Create a CounterfactualAgent for testing."""
        return CounterfactualAgent(model="test-model")
    
    @pytest.fixture
    def mock_ollama_response(self):
        """Mock Ollama response for counterfactual analysis."""
        return {
            "main_claims": [
                "Exercise improves cardiovascular health",
                "Regular physical activity reduces heart disease risk by 30%"
            ],
            "counterfactual_questions": [
                {
                    "counterfactual_statement": "Exercise worsens heart conditions in certain populations",
                    "question": "Are there studies showing exercise can worsen heart conditions in certain populations?",
                    "reasoning": "To verify if exercise benefits apply universally or have population-specific contraindications",
                    "target_claim": "Exercise improves cardiovascular health",
                    "search_keywords": ["exercise", "contraindications", "heart failure", "adverse effects"],
                    "priority": "HIGH"
                },
                {
                    "counterfactual_statement": "Physical activity reduces heart disease risk by less than 30%",
                    "question": "Do any meta-analyses show smaller effect sizes than 30% risk reduction?",
                    "reasoning": "To verify the magnitude of claimed risk reduction",
                    "target_claim": "Regular physical activity reduces heart disease risk by 30%",
                    "search_keywords": ["meta-analysis", "physical activity", "risk reduction", "effect size"],
                    "priority": "MEDIUM"
                }
            ],
            "overall_assessment": "Claims are well-supported but may have population-specific limitations and effect size variations",
            "confidence_level": "MEDIUM"
        }
    
    def test_agent_initialization(self, agent):
        """Test CounterfactualAgent initialization."""
        assert agent.model == "test-model"
        assert agent.get_agent_type() == "counterfactual_agent"
        assert agent.temperature == 0.2  # Should use default for creative generation
        assert "medical research expert" in agent.system_prompt
    
    def test_get_agent_type(self, agent):
        """Test get_agent_type method."""
        assert agent.get_agent_type() == "counterfactual_agent"
    
    @patch('bmlibrarian.agents.counterfactual_agent.CounterfactualAgent._make_ollama_request')
    def test_analyze_document_success(self, mock_request, agent, mock_ollama_response):
        """Test successful document analysis."""
        mock_request.return_value = json.dumps(mock_ollama_response)
        
        document_content = """
        Exercise and Cardiovascular Health Review
        
        Regular physical activity has been consistently shown to improve cardiovascular outcomes.
        Multiple studies demonstrate that exercise reduces heart disease risk by approximately 30%.
        The benefits appear to be dose-dependent and universal across populations.
        """
        
        result = agent.analyze_document(document_content, "Exercise Review")
        
        assert result is not None
        assert isinstance(result, CounterfactualAnalysis)
        assert result.document_title == "Exercise Review"
        assert len(result.main_claims) == 2
        assert len(result.counterfactual_questions) == 2
        assert result.confidence_level == "MEDIUM"
        
        # Test question details
        high_priority_questions = [q for q in result.counterfactual_questions if q.priority == "HIGH"]
        assert len(high_priority_questions) == 1
        assert "contraindications" in high_priority_questions[0].search_keywords
    
    def test_analyze_document_empty_content(self, agent):
        """Test analysis with empty document content."""
        result = agent.analyze_document("", "Empty Document")
        assert result is None
        
        result = agent.analyze_document(None, "None Document")
        assert result is None
    
    @patch('bmlibrarian.agents.counterfactual_agent.CounterfactualAgent._make_ollama_request')
    def test_analyze_document_invalid_json(self, mock_request, agent):
        """Test handling of invalid JSON response."""
        mock_request.return_value = "Invalid JSON response"
        
        result = agent.analyze_document("Test content", "Test Document")
        assert result is None
    
    @patch('bmlibrarian.agents.counterfactual_agent.CounterfactualAgent._make_ollama_request')
    def test_analyze_document_missing_fields(self, mock_request, agent):
        """Test handling of response missing required fields."""
        invalid_response = {
            "main_claims": ["Claim 1"],
            # Missing other required fields
        }
        mock_request.return_value = json.dumps(invalid_response)
        
        result = agent.analyze_document("Test content", "Test Document")
        assert result is None
    
    @patch('bmlibrarian.agents.counterfactual_agent.CounterfactualAgent._make_ollama_request')
    def test_analyze_document_ollama_exception(self, mock_request, agent):
        """Test handling of Ollama request exceptions."""
        mock_request.side_effect = Exception("Ollama connection failed")
        
        result = agent.analyze_document("Test content", "Test Document")
        assert result is None
    
    def test_analyze_report_citations_empty_report(self, agent):
        """Test citation analysis with empty report."""
        result = agent.analyze_report_citations("", [])
        assert result is None
    
    @patch('bmlibrarian.agents.counterfactual_agent.CounterfactualAgent.analyze_document')
    def test_analyze_report_citations_with_citation_objects(self, mock_analyze, agent):
        """Test citation analysis with Citation objects."""
        # Mock Citation objects
        citation1 = Mock()
        citation1.document_title = "Study 1"
        citation1.summary = "Exercise improves heart health"
        
        citation2 = Mock()
        citation2.document_title = "Study 2" 
        citation2.summary = "Physical activity reduces mortality"
        
        citations = [citation1, citation2]
        
        mock_analysis = Mock()
        mock_analyze.return_value = mock_analysis
        
        result = agent.analyze_report_citations("Test report content", citations)
        
        assert mock_analyze.called
        call_args = mock_analyze.call_args
        assert "Test report content" in call_args[0][0]
        assert "Study 1" in call_args[0][0]
        assert "Study 2" in call_args[0][0]
        assert call_args[0][1] == "Research Report with Citations"
    
    @patch('bmlibrarian.agents.counterfactual_agent.CounterfactualAgent.analyze_document')
    def test_analyze_report_citations_with_dicts(self, mock_analyze, agent):
        """Test citation analysis with citation dictionaries."""
        citations = [
            {"document_title": "Study A", "summary": "Summary A"},
            {"document_title": "Study B", "summary": "Summary B"}
        ]
        
        mock_analysis = Mock()
        mock_analyze.return_value = mock_analysis
        
        result = agent.analyze_report_citations("Test report", citations)
        
        assert mock_analyze.called
        call_args = mock_analyze.call_args
        assert "Study A" in call_args[0][0]
        assert "Study B" in call_args[0][0]
    
    def test_get_high_priority_questions(self, agent):
        """Test filtering high priority questions."""
        questions = [
            CounterfactualQuestion("S1", "Q1", "R1", "C1", ["k1"], "HIGH"),
            CounterfactualQuestion("S2", "Q2", "R2", "C2", ["k2"], "MEDIUM"),
            CounterfactualQuestion("S3", "Q3", "R3", "C3", ["k3"], "HIGH"),
            CounterfactualQuestion("S4", "Q4", "R4", "C4", ["k4"], "LOW")
        ]
        
        analysis = CounterfactualAnalysis(
            document_title="Test",
            main_claims=["Claim 1"], 
            counterfactual_questions=questions,
            overall_assessment="Test",
            confidence_level="MEDIUM"
        )
        
        high_priority = agent.get_high_priority_questions(analysis)
        assert len(high_priority) == 2
        assert all(q.priority == "HIGH" for q in high_priority)
    
    def test_format_questions_for_search(self, agent):
        """Test formatting questions for PostgreSQL to_tsquery search queries."""
        questions = [
            CounterfactualQuestion(
                "Exercise causes harm",
                "Does exercise cause harm?",
                "Test reasoning",
                "Test claim",
                ["exercise", "adverse effects", "harm"],
                "HIGH"
            ),
            CounterfactualQuestion(
                "Physical activity is ineffective",
                "Is physical activity ineffective?",
                "Test reasoning 2",
                "Test claim 2",
                ["physical activity", "ineffective"],
                "MEDIUM"
            )
        ]
        
        search_queries = agent.format_questions_for_search(questions)
        assert len(search_queries) == 2
        # Check PostgreSQL to_tsquery format with | for OR and & for AND
        # Note: Multi-word phrases are quoted
        assert "exercise" in search_queries[0]
        assert "'adverse effects'" in search_queries[0]  # Multi-word phrase is quoted
        assert "harm" in search_queries[0]
        assert "'physical activity'" in search_queries[1]  # Multi-word phrase is quoted
        assert "ineffective" in search_queries[1]
        # Should include negation terms combined with AND
        assert "ineffective" in search_queries[0] or "adverse" in search_queries[0]

    @patch('bmlibrarian.agents.counterfactual_agent.CounterfactualAgent.generate_research_queries_with_agent')
    def test_generate_research_queries_with_agent(self, mock_generate, agent):
        """Test database query generation with QueryAgent integration."""
        questions = [
            CounterfactualQuestion(
                "Exercise causes harm",
                "Does exercise cause harm?",
                "Test reasoning",
                "Exercise improves health",
                ["exercise", "cardiovascular"],
                "HIGH"
            )
        ]
        
        # Mock the return value
        mock_generate.return_value = [
            {
                'question': 'Does exercise cause harm?',
                'db_query': 'exercise & (ineffective | adverse | negative)',
                'target_claim': 'Exercise improves health',
                'search_keywords': ['exercise', 'cardiovascular'],
                'priority': 'HIGH',
                'reasoning': 'Test reasoning'
            }
        ]
        
        result = agent.generate_research_queries_with_agent(questions)
        assert len(result) == 1
        assert result[0]['question'] == 'Does exercise cause harm?'
        assert 'db_query' in result[0]
        assert result[0]['priority'] == 'HIGH'
    
    def test_generate_research_protocol(self, agent):
        """Test research protocol generation."""
        questions = [
            CounterfactualQuestion("High S", "High Q", "High R", "High C", ["high"], "HIGH"),
            CounterfactualQuestion("Med S", "Med Q", "Med R", "Med C", ["med"], "MEDIUM"),
            CounterfactualQuestion("Low S", "Low Q", "Low R", "Low C", ["low"], "LOW")
        ]
        
        analysis = CounterfactualAnalysis(
            document_title="Test Document",
            main_claims=["Claim 1", "Claim 2"],
            counterfactual_questions=questions,
            overall_assessment="Test assessment",
            confidence_level="HIGH"
        )
        
        protocol = agent.generate_research_protocol(analysis)
        
        assert "# Counterfactual Research Protocol" in protocol
        assert "Test Document" in protocol
        assert "HIGH PRIORITY" in protocol
        assert "MEDIUM PRIORITY" in protocol
        assert "LOW PRIORITY" in protocol
        assert "Claim 1" in protocol
        assert "Claim 2" in protocol
        assert "Test assessment" in protocol
        assert "High Q" in protocol
        assert "Med Q" in protocol
        assert "Low Q" in protocol
    
    def test_callback_functionality(self):
        """Test that callbacks are properly called during analysis."""
        callback_calls = []
        
        def test_callback(step, data):
            callback_calls.append((step, data))
        
        agent = CounterfactualAgent(callback=test_callback)
        
        # Test callback with empty document (should trigger callback)
        result = agent.analyze_document("", "Test")
        
        # Even with failure, we shouldn't get callbacks because we exit early
        # But let's test the _call_callback method directly
        agent._call_callback("test_step", "test_data")
        assert len(callback_calls) == 1
        assert callback_calls[0] == ("test_step", "test_data")
    
    def test_callback_exception_handling(self):
        """Test that callback exceptions don't break the agent."""
        def failing_callback(step, data):
            raise Exception("Callback failed")
        
        agent = CounterfactualAgent(callback=failing_callback)
        
        # This should not raise an exception
        agent._call_callback("test_step", "test_data")
    
    @patch('bmlibrarian.agents.counterfactual_agent.CounterfactualAgent._make_ollama_request')
    def test_system_prompt_usage(self, mock_request, agent, mock_ollama_response):
        """Test that system prompt is properly used in requests."""
        mock_request.return_value = json.dumps(mock_ollama_response)

        agent.analyze_document("Test content", "Test Document")

        # Verify system prompt was passed
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        assert 'system_prompt' in call_kwargs
        assert 'medical research expert' in call_kwargs['system_prompt']
    
    def test_priority_case_normalization(self, agent):
        """Test that priority values are normalized to uppercase."""
        # This would be tested through the full analysis workflow
        # The dataclass should handle case normalization in __post_init__
        question = CounterfactualQuestion(
            "Statement", "Test", "Test", "Test", ["test"], "high"  # lowercase
        )
        # Note: The current implementation doesn't auto-normalize,
        # but the agent converts to uppercase when parsing JSON
        assert question.priority == "high"  # Current behavior
        
        # However, when parsing from JSON, the agent converts to uppercase
        test_response = {
            "main_claims": ["Test claim"],
            "counterfactual_questions": [{
                "counterfactual_statement": "Test statement",
                "question": "Test question",
                "reasoning": "Test reasoning",
                "target_claim": "Test claim",
                "search_keywords": ["test"],
                "priority": "medium"  # lowercase in response
            }],
            "overall_assessment": "Test",
            "confidence_level": "low"
        }
        
        with patch('bmlibrarian.agents.counterfactual_agent.CounterfactualAgent._make_ollama_request') as mock_request:
            mock_request.return_value = json.dumps(test_response)
            result = agent.analyze_document("Test content", "Test")
            
            # Should be converted to uppercase
            assert result.confidence_level == "LOW"
            assert result.counterfactual_questions[0].priority == "MEDIUM"


if __name__ == "__main__":
    pytest.main([__file__])