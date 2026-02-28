import { useState } from "react";
import type { Agent } from "../types";

interface AgentFormData {
  name: string;
  type: string;
  model: string;
  system_prompt: string;
}

interface AgentModalProps {
  editingAgent: Agent | null;
  initialData: AgentFormData;
  onSave: (data: AgentFormData) => void;
  onClose: () => void;
}

export function AgentModal({
  editingAgent,
  initialData,
  onSave,
  onClose,
}: AgentModalProps) {
  const [formData, setFormData] = useState<AgentFormData>(initialData);
  const [nameError, setNameError] = useState("");

  const handleSave = () => {
    if (!formData.name.trim()) {
      setNameError("Agent name is required");
      return;
    }
    setNameError("");
    onSave(formData);
  };

  return (
    <div
      className="modal-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="agent-modal-title"
    >
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3
          id="agent-modal-title"
          className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-5"
        >
          {editingAgent ? "Edit Agent" : "Create New Agent"}
        </h3>

        <div className="space-y-4">
          <div>
            <label
              htmlFor="agent-name"
              className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5"
            >
              Agent Name
            </label>
            <input
              id="agent-name"
              className={`input w-full ${nameError ? "ring-2 ring-red-500/40 border-red-500" : ""}`}
              placeholder="e.g., Research Assistant, Code Helper..."
              value={formData.name}
              onChange={(e) => {
                setFormData({ ...formData, name: e.target.value });
                if (nameError) setNameError("");
              }}
              autoFocus
            />
            {nameError && (
              <p className="text-xs text-red-500 mt-1">{nameError}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="agent-type"
              className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5"
            >
              Agent Type
            </label>
            <select
              id="agent-type"
              className="input w-full"
              value={formData.type}
              onChange={(e) =>
                setFormData({ ...formData, type: e.target.value })
              }
              disabled={!!editingAgent}
            >
              <option value="general">General Purpose</option>
              <option value="browser">Browser / Web Research</option>
              <option value="research">Deep Research</option>
              <option value="code">Code Generation</option>
              <option value="communication">Communication</option>
            </select>
            {editingAgent && (
              <p className="text-xs text-gray-400 mt-1">
                Agent type cannot be changed after creation
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="agent-model"
              className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5"
            >
              AI Model
            </label>
            <select
              id="agent-model"
              className="input w-full"
              value={formData.model}
              onChange={(e) =>
                setFormData({ ...formData, model: e.target.value })
              }
            >
              <option value="claude-opus-4-6">Claude Opus 4.6</option>
              <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
              <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
              <option value="gpt-4o">GPT-4o</option>
              <option value="ollama/llama3">Ollama Llama 3</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="agent-prompt"
              className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5"
            >
              System Prompt{" "}
              <span className="normal-case tracking-normal font-normal">
                (optional)
              </span>
            </label>
            <textarea
              id="agent-prompt"
              className="input w-full h-24 resize-none text-sm"
              placeholder="Custom instructions for this agent... Leave empty for defaults."
              value={formData.system_prompt}
              onChange={(e) =>
                setFormData({ ...formData, system_prompt: e.target.value })
              }
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button className="btn-secondary cursor-pointer" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn-gold cursor-pointer"
            onClick={handleSave}
            disabled={!formData.name.trim()}
          >
            {editingAgent ? "Save Changes" : "Create Agent"}
          </button>
        </div>
      </div>
    </div>
  );
}
