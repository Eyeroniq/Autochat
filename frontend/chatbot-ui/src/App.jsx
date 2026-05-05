import { useState } from "react";

function App() {
  const [messages, setMessages] = useState([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);

  const sendQuery = async () => {
    if (!query.trim()) return;

    const userMessage = { role: "user", text: query };

    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    const res = await fetch("http://localhost:8000/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    });

    const data = await res.json();

    const botMessage = {
      role: "bot",
      text: data.response,
      query: query, // 🔥 VERY IMPORTANT (store original question)
    };

    setMessages((prev) => [...prev, botMessage]);
    setQuery("");
    setLoading(false);
  };

  // 🔥 Feedback function
  const sendFeedback = async (query) => {
    await fetch("http://localhost:8000/feedback", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query: query,
        feedback: "no",
      }),
    });

    alert("Saved for improvement ✅");
  };

  return (
    <div style={{ maxWidth: "600px", margin: "auto", padding: "20px" }}>
      <h1>💬 AI Chatbot</h1>

      <div style={{ minHeight: "400px" }}>
        {messages.map((msg, index) => (
          <div key={index} style={{ marginBottom: "10px" }}>
            
            <div
              style={{
                textAlign: msg.role === "user" ? "right" : "left",
              }}
            >
              <span
                style={{
                  display: "inline-block",
                  padding: "10px",
                  borderRadius: "10px",
                  background:
                    msg.role === "user" ? "#007bff" : "#e5e5ea",
                  color: msg.role === "user" ? "white" : "black",
                }}
              >
                {msg.text}
              </span>
            </div>

            {/* 🔥 Show button ONLY for bot responses */}
            {msg.role === "bot" && (
              <button
                onClick={() => sendFeedback(msg.query)}
                style={{
                  fontSize: "12px",
                  marginTop: "4px",
                  cursor: "pointer",
                }}
              >
                ❌ Not Useful
              </button>
            )}
          </div>
        ))}

        {loading && <p>Thinking...</p>}
      </div>

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Ask something..."
        style={{ width: "75%", padding: "10px" }}
      />

      <button onClick={sendQuery} style={{ padding: "10px" }}>
        Send
      </button>
    </div>
  );
}

export default App;