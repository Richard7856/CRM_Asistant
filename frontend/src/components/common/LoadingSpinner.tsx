export default function LoadingSpinner({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center justify-center p-8 ${className}`}>
      <div className="neu-pressed w-14 h-14 rounded-full flex items-center justify-center">
        <div className="w-7 h-7 rounded-full border-[3px] border-[var(--neu-dark)] border-t-indigo-500 animate-spin" />
      </div>
    </div>
  );
}
