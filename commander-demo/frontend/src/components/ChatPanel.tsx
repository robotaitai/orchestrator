import { useState, useRef, useEffect } from 'react';
import { sendCommand, type CommandResult } from '../api';
import './ChatPanel.css';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  type?: string;
  traceId?: string;
  timestamp: Date;
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Commander ready. Enter a natural language command to control the fleet.',
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: input,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const result: CommandResult = await sendCommand(input);
      
      let assistantContent = '';
      if (result.type === 'commands') {
        const cmds = result.commands?.map(c => `${c.command}(${c.target})`).join(', ') || '';
        assistantContent = `✓ ${result.explanation || 'Commands executed'}\n\nCommands: ${cmds}`;
        if (result.tasks) {
          const taskInfo = result.tasks.map(t => `${t.id}: ${t.status}`).join(', ');
          assistantContent += `\nTasks: ${taskInfo}`;
        }
      } else if (result.type === 'clarification') {
        assistantContent = `❓ ${result.question}`;
        if (result.options?.length) {
          assistantContent += `\n\nOptions:\n${result.options.map(o => `• ${o}`).join('\n')}`;
        }
      } else if (result.type === 'response') {
        assistantContent = result.message || 'OK';
      } else if (result.type === 'error') {
        assistantContent = `⚠️ Error: ${result.error}\n${result.details || ''}`;
      }

      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: assistantContent,
        type: result.type,
        traceId: result.trace_id,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: `⚠️ Connection error: ${error}`,
        type: 'error',
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <span className="chat-title">COMMAND INTERFACE</span>
      </div>
      
      <div className="chat-messages">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`message ${message.role} ${message.type || ''} animate-slide-in`}
          >
            <div className="message-content">{message.content}</div>
            {message.traceId && (
              <div className="message-trace">
                <code>{message.traceId}</code>
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div className="message assistant loading">
            <div className="typing-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      
      <form className="chat-input" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Enter command..."
          disabled={isLoading}
          autoFocus
        />
        <button type="submit" disabled={isLoading || !input.trim()}>
          SEND
        </button>
      </form>
    </div>
  );
}
