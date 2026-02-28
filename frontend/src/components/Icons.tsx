import {
  MessageCircle,
  Send,
  Trash2,
  Globe,
  Zap,
  Shield,
  Clock,
  Settings,
  Sun,
  Moon,
  Monitor,
  BookOpen,
  Plus,
  Search,
  Code,
  Users,
} from "lucide-react";

const svgProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  className: "w-5 h-5",
  "aria-hidden": true as const,
};

export const Icons = {
  Agent: () => (
    <svg {...svgProps}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c0-4 3.58-7 8-7s8 3 8 7" />
      <path d="M20 12h2M2 12h2M12 2v2M12 20v2" />
    </svg>
  ),
  Brain: () => (
    <svg {...svgProps}>
      <path d="M12 5c-2.8 0-5 2.2-5 5 0 1.5.6 2.8 1.5 3.8C7.2 15 6 17 6 19h12c0-2 -1.2-4-2.5-5.2C16.4 12.8 17 11.5 17 10c0-2.8-2.2-5-5-5z" />
      <path d="M9 10h6M10 13h4" />
    </svg>
  ),
  Terminal: () => (
    <svg {...svgProps}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M7 9l3 3-3 3M13 15h4" />
    </svg>
  ),
  Memory: () => (
    <svg {...svgProps}>
      <rect x="2" y="7" width="20" height="10" rx="2" />
      <path d="M7 7V5M12 7V5M17 7V5M7 17v2M12 17v2M17 17v2" />
      <circle cx="7" cy="12" r="1.5" fill="currentColor" />
      <circle cx="12" cy="12" r="1.5" fill="currentColor" />
      <circle cx="17" cy="12" r="1.5" fill="currentColor" />
    </svg>
  ),
  Chat: () => <MessageCircle className="w-5 h-5" aria-hidden="true" />,
  Plus: () => <Plus className="w-4 h-4" aria-hidden="true" />,
  Send: () => <Send className="w-4 h-4" aria-hidden="true" />,
  Trash: () => <Trash2 className="w-4 h-4" aria-hidden="true" />,
  Globe: () => <Globe className="w-5 h-5" aria-hidden="true" />,
  Zap: () => <Zap className="w-5 h-5" aria-hidden="true" />,
  Channel: () => (
    <svg {...svgProps}>
      <path d="M4 11a9 9 0 0 1 9 9M4 4a16 16 0 0 1 16 16" />
      <circle cx="5" cy="19" r="2" fill="currentColor" />
    </svg>
  ),
  Skill: () => (
    <svg {...svgProps}>
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </svg>
  ),
  Shield: () => <Shield className="w-5 h-5" aria-hidden="true" />,
  Clock: () => <Clock className="w-5 h-5" aria-hidden="true" />,
  Notebook: () => (
    <svg {...svgProps}>
      <path d="M4 4h16v16H4z" />
      <path d="M8 4v16M4 8h4M4 12h4M4 16h4" />
      <path d="M11 8h6M11 12h4" />
    </svg>
  ),
  Plugin: () => (
    <svg {...svgProps}>
      <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
      <rect x="8" y="8" width="8" height="8" rx="1" />
      <path d="M10 8V6a2 2 0 114 0v2M8 14h-2a2 2 0 100 4h2" />
    </svg>
  ),
  Eye: () => (
    <svg {...svgProps}>
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ),
  Sun: () => <Sun className="w-5 h-5" aria-hidden="true" />,
  Moon: () => <Moon className="w-5 h-5" aria-hidden="true" />,
  Monitor: () => <Monitor className="w-5 h-5" aria-hidden="true" />,
  Book: () => <BookOpen className="w-5 h-5" aria-hidden="true" />,
  Settings: () => <Settings className="w-5 h-5" aria-hidden="true" />,
  Search: () => <Search className="w-5 h-5" aria-hidden="true" />,
  Code: () => <Code className="w-5 h-5" aria-hidden="true" />,
  Users: () => <Users className="w-5 h-5" aria-hidden="true" />,
};
