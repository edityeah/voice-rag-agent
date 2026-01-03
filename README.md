# Real time RAG Voice Agent, powered by Cartesia

This project implements a VOICE RAG Agent powered by [Cartesia](https://play.cartesia.ai/)

## Installation

Ensure you have Python 3.11 or later installed and run:

```bash
pip install -r requirements.txt
```

## Implementation 1: voice_agent_openai.py

This implementation uses OpenAI's services for speech-to-text and cartesia for speech synthesis, simpler setup if you already have OpenAI API keys.

### Requirements
1. [Cartesia AI key](https://play.cartesia.ai/)
2. OpenAI API key
3. [LiveKit credentials](https://livekit.io/)

### Setup
1. Copy `.env.example` to `.env`
2. Configure the following environment variables:
```bash
OPENAI_API_KEY=your_openai_api_key
CARTESIA_API_KEY=your_cartesia_api_key
LIVEKIT_URL=your_livekit_url
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
ASSEMBLYAI_API_KEY=your_assemblyai_api_key
```

### Running
```bash
python voice_agent_openai.py start
```

### Connecting to Agent Playground

[Livekit Agents Playground](https://agents-playground.livekit.io/)

## Implementation 2: voice_agent.py

This implementation uses AssemblyAI for speech processing and Ollama (with Gemma) for language tasks.

### Setup

1. **Install Ollama**
   ```bash
   # For macOS
   brew install ollama
   
   # For Linux
   curl -fsSL https://ollama.com/install.sh | sh
   ```

2. **Pull Gemma Model**
   ```bash
   ollama pull gemma3
   ```

3. **Configure Environment**
   Copy `.env.example` to `.env` and set:
   ```bash
   CARTESIA_API_KEY=your_cartesia_api_key
   LIVEKIT_URL=your_livekit_url
   LIVEKIT_API_KEY=your_livekit_api_key
   LIVEKIT_API_SECRET=your_livekit_api_secret
   ASSEMBLYAI_API_KEY=your_assemblyai_api_key
   ```

### Running
1. Start Ollama server:
   ```bash
   ollama serve
   ```

2. In a new terminal, run the voice agent:
   ```bash
   python voice_agent.py start
   ```

---

## ✍️ About the Author
Built by Adityeah

I build AI agents that solve real human problems, not just productivity ones.

📰 Read the full breakdown in my newsletter: [Adityeah's Newletter](https://news.adityeah.in/)

🤝 Connect on LinkedIn: [Aditya Chaudhari](https://www.linkedin.com/in/adityacbcc/)

---

## Contribution

Contributions are welcome! Please fork the repository and submit a pull request with your improvements.

