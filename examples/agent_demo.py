#!/usr/bin/env python3
"""
Demo script showing how to use the QueryAgent for converting biomedical questions
into PostgreSQL to_tsquery format.
"""

from bmlibrarian.agents import QueryAgent


def main():
    """Demonstrate the QueryAgent functionality."""
    print("🧬 Biomedical Query Agent Demo")
    print("=" * 50)
    
    # Initialize the agent
    agent = QueryAgent()
    
    # Test connection
    print("\n📡 Testing connection to Ollama...")
    if not agent.test_connection():
        print("❌ Failed to connect to Ollama. Please ensure:")
        print("   1. Ollama is running (try: ollama serve)")
        print("   2. The medgemma4B_it_q8:latest model is available")
        print("   3. Run: ollama pull medgemma4B_it_q8:latest")
        return
    
    print("✅ Connection successful!")
    
    # Show available models
    try:
        models = agent.get_available_models()
        print(f"\n🎯 Available models: {len(models)} models found")
        print(f"Using model: {agent.model}")
    except Exception as e:
        print(f"Warning: Could not retrieve model list: {e}")
    
    # Demo questions
    demo_questions = [
        "What are the effects of aspirin on cardiovascular disease?",
        "How does diabetes affect kidney function?",
        "Studies on COVID-19 vaccine effectiveness",
        "Side effects of statins in elderly patients",
        "Treatment options for rheumatoid arthritis",
        "Biomarkers for early Alzheimer's diagnosis",
        "Gene therapy for sickle cell disease clinical trials",
        "Effectiveness of immunotherapy for lung cancer"
    ]
    
    print("\n🔍 Converting biomedical questions to database queries:")
    print("-" * 60)
    
    for i, question in enumerate(demo_questions, 1):
        print(f"\n{i}. Question:")
        print(f"   {question}")
        
        try:
            query = agent.convert_question(question)
            print(f"   PostgreSQL query:")
            print(f"   {query}")
            
            # Validate the query
            if agent._validate_tsquery(query):
                print("   ✅ Query format is valid")
            else:
                print("   ⚠️  Query format may have issues")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print(f"\n🎉 Demo completed! The QueryAgent successfully converted")
    print(f"    {len(demo_questions)} biomedical questions into database-ready queries.")
    
    # Interactive mode
    print("\n💬 Interactive Mode (type 'quit' to exit):")
    print("-" * 40)
    
    while True:
        try:
            question = input("\nEnter your biomedical question: ").strip()
            
            if question.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            
            if not question:
                continue
                
            query = agent.convert_question(question)
            print(f"Generated query: {query}")
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()