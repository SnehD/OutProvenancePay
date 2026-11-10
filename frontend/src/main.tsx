import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { WorkflowProvider } from './state/workflow';
import './styles.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <WorkflowProvider>
      <App />
    </WorkflowProvider>
  </StrictMode>,
);
