// frontend/src/App.tsx
import { useExtraction } from "./hooks/useExtraction";
import UploadView from "./components/UploadView";
import ProcessingView from "./components/ProcessingView";
import ResultsView from "./components/ResultsView";

export default function App() {
  const { startUpload, startSample, progress, result, error, isLoading, reset } =
    useExtraction();

  // View state derived from hook state
  if (result) {
    return <ResultsView result={result} onReset={reset} />;
  }

  if (isLoading || error) {
    return <ProcessingView progress={progress} error={error} onReset={reset} />;
  }

  return <UploadView onFileSelect={startUpload} onSampleSelect={startSample} />;
}
