# SRR Case Processing Chatbot Interface

This is a chatbot-style interface developed with React and TypeScript for SRR case file processing and information extraction.

## Features

### 🤖 Chatbot Interface
- Modern chat interface design
- Real-time message interaction
- Intelligent response and query processing
- User-friendly conversation experience

### 📁 File Processing
- **Drag & Drop Upload**: Supports dragging files to designated areas
- **File Type Support**: PDF and TXT files
- **File Validation**: Automatic file type and size validation
- **Real-time Processing**: Asynchronous file processing with status feedback

### 📊 Information Display
- **Structured Display**: Complete A-Q field display
- **Categorized Organization**: Information grouped by function
- **Visual Indicators**: Uses icons and colors to distinguish different types of information
- **Null Value Handling**: Graceful handling of missing data

### 🔍 Smart Query
- **Contextual Query**: Intelligent Q&A based on extracted information
- **Keyword Matching**: Supports multiple query patterns
- **Instant Response**: Fast query responses
- **Query Suggestions**: Provides query examples and suggestions

### 📱 Responsive Design
- **Mobile Adaptation**: Fully responsive layout
- **Cross-device Compatibility**: Supports desktop and mobile
- **Touch-friendly**: Optimized touch interaction experience

## Tech Stack

- **React 18**: Modern React framework
- **TypeScript**: Type-safe JavaScript
- **React Dropzone**: File drag and drop upload
- **Axios**: HTTP client
- **Lucide React**: Modern icon library
- **CSS3**: Modern CSS styles and animations

## Project Structure

```
src/
├── components/           # React components
│   ├── ChatbotInterface.tsx    # Main chat interface
│   └── ExtractedInfoDisplay.tsx # Information display component
├── services/            # API services
│   └── api.ts          # API call encapsulation
├── types/              # TypeScript type definitions
│   └── index.ts        # Common types
├── App.tsx             # Main application component
├── App.css             # Global styles
└── index.tsx           # Application entry point
```

## Installation and Setup

### Prerequisites
- Node.js 16+
- npm or yarn

### Install Dependencies
```bash
npm install
```

### Start Development Server
```bash
npm start
```

Application will start at http://localhost:3000

### Build for Production
```bash
npm run build
```

## API Integration

The application needs to connect to a backend API server, default address is `http://localhost:8000`

### API Endpoints
- `POST /api/process-srr-file` - File processing
- `GET /health` - Health check

### Environment Configuration
API address can be configured through environment variables:
```bash
REACT_APP_API_URL=http://your-api-server:8000
```

## Usage Guide

### 1. File Upload
- Drag PDF or TXT files to the right upload area
- Or click the upload area to select files
- Supported formats: PDF, TXT
- Maximum file size: 10MB

### 2. Information Viewing
- After file processing is complete, extracted information will be displayed on the right
- Information is displayed categorized by A-Q fields
- Empty values will be shown as "Not provided"

### 3. Smart Query
- Enter questions in the bottom input field
- Supported query types:
  - Basic case information
  - Contact information
  - Slope-related information
  - Important dates
  - Case nature

### 4. Query Examples
- "What is the basic information of this case?"
- "Contact information"
- "Slope-related information"
- "Important dates"
- "Case nature"

## Design Features

### 🎨 Visual Design
- **Modern Gradient**: Uses purple gradient theme
- **Card Design**: Information displayed in card format
- **Icon System**: Unified icon language
- **Animation Effects**: Smooth interaction animations

### 💬 Chat Experience
- **Message Bubbles**: Distinguishes user and bot messages
- **Avatar System**: Visual representation of conversation participants
- **Timestamps**: Message time records
- **Status Indicators**: Loading and processing states

### 📋 Information Architecture
- **Layered Display**: Important information displayed first
- **Grouped Organization**: Related information grouped together
- **Status Indicators**: Clear status indications
- **Null Value Handling**: Graceful handling of missing data

## Browser Support

- Chrome 80+
- Firefox 75+
- Safari 13+
- Edge 80+

## Development Guide

### Adding New Query Types
1. Add new query logic in the `queryCaseStream` function (or corresponding stream API) in `services/api.ts`
2. Update related type definitions in `types/index.ts`
3. Add corresponding query suggestions in the chat interface

### Customizing Styles
Main style file is in `src/App.css`, including:
- Chat interface styles
- File upload area styles
- Information display styles
- Responsive media queries

### Extending File Type Support
1. Update file validation logic in `ChatbotInterface.tsx` and upload components
2. Set `REACT_APP_API_URL` for API endpoint
3. Ensure backend API supports new file types

## License

MIT License