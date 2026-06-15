export default function Home() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex flex-col items-center gap-4 text-center">
        <h1 className="text-5xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Heron
        </h1>
        <p className="max-w-md text-lg text-zinc-600 dark:text-zinc-400">
          The Splunk app that builds and maintains itself.
        </p>
      </main>
    </div>
  );
}
