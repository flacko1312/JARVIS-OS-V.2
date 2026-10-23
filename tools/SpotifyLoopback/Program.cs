using NAudio.CoreAudioApi;
using NAudio.Wave;

if (args.Length < 1 || !uint.TryParse(args[0], out var targetPid))
{
    Console.Error.WriteLine("Usage: SpotifyLoopback <spotify-root-pid>");
    return 2;
}

var format = new WaveFormat(16000, 16, 1);
using var cts = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

try
{
    await using var recorder = await new WasapiRecorderBuilder()
        .WithProcessLoopback(targetPid, ProcessLoopbackMode.IncludeTargetProcessTree)
        .WithFormat(format)
        .WithBufferLength(20)
        .WithMmcssThreadPriority("Audio")
        .BuildAsync();

    Console.Error.WriteLine($"READY pid={targetPid} format=16000/16/1");
    await using var stdout = Console.OpenStandardOutput();

    try
    {
        await foreach (var buffer in recorder.CaptureAsync(cts.Token))
        {
            await stdout.WriteAsync(buffer.Data, cts.Token);
        }
    }
    catch (OperationCanceledException) when (cts.IsCancellationRequested)
    {
    }

    return 0;
}
catch (Exception ex)
{
    Console.Error.WriteLine($"ERROR {ex.GetType().Name}: {ex.Message}");
    return 1;
}
