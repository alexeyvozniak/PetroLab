using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Windows.Forms;

internal static class Program
{
    private static readonly object LogSync = new object();
    private static string LogFile = "";

    [STAThread]
    private static void Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        string current = Path.Combine(root, "current");
        string python = Path.Combine(root, "runtime", "python.exe");
        string app = Path.Combine(current, "app.py");
        string logDir = Path.Combine(root, "logs");
        string stateFile = Path.Combine(root, "petrolab-server.state");
        Mutex launchMutex = null;
        bool ownsMutex = false;

        try
        {
            Directory.CreateDirectory(logDir);
            LogFile = Path.Combine(logDir, "launcher.log");
            WriteLog("--- PetroLab launcher start ---");

            if (!File.Exists(python))
            {
                Fail("Embedded PetroLab Python runtime is missing. Reinstall PetroLab or run Diagnostics.");
                return;
            }
            if (!File.Exists(app))
            {
                Fail("PetroLab app.py is missing. Reinstall PetroLab or run Diagnostics.");
                return;
            }

            int existingPort;
            if (TryExistingServer(stateFile, out existingPort))
            {
                WriteLog("Existing healthy server found on port " + existingPort + ".");
                OpenBrowser(existingPort);
                return;
            }

            launchMutex = new Mutex(false, @"Local\PetroLab-Native-Launcher");
            try
            {
                ownsMutex = launchMutex.WaitOne(0, false);
            }
            catch (AbandonedMutexException)
            {
                ownsMutex = true;
                WriteLog("Recovered abandoned launcher mutex.");
            }

            if (!ownsMutex)
            {
                WriteLog("Another PetroLab launcher is starting; waiting for its server state.");
                for (int attempt = 0; attempt < 120; attempt++)
                {
                    if (TryExistingServer(stateFile, out existingPort))
                    {
                        WriteLog("Startup completed in another launcher on port " + existingPort + ".");
                        OpenBrowser(existingPort);
                        return;
                    }
                    Thread.Sleep(250);
                }
                Fail("PetroLab is already starting, but it did not become ready in time. Try again in a moment or run Diagnostics.");
                return;
            }

            // Re-check after acquiring the startup mutex in case another process
            // published a healthy server between our first check and lock acquisition.
            if (TryExistingServer(stateFile, out existingPort))
            {
                WriteLog("Healthy server appeared before startup lock acquisition on port " + existingPort + ".");
                OpenBrowser(existingPort);
                return;
            }

            string dataDir = Environment.GetEnvironmentVariable("PETROLAB_DATA_DIR") ?? "";
            if (String.IsNullOrWhiteSpace(dataDir))
            {
                string documents = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
                if (String.IsNullOrWhiteSpace(documents))
                {
                    documents = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Documents");
                }
                dataDir = Path.Combine(documents, "PetroLab Data");
            }
            Directory.CreateDirectory(dataDir);

            int port = FindFreePort();
            string arguments = "-m streamlit run " + Quote(app)
                + " --server.headless=true"
                + " --server.address=127.0.0.1"
                + " --server.port=" + port
                + " --browser.gatherUsageStats=false";

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = python;
            psi.Arguments = arguments;
            psi.WorkingDirectory = current;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.WindowStyle = ProcessWindowStyle.Hidden;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.EnvironmentVariables["PETROLAB_DATA_DIR"] = dataDir;

            Process server = new Process();
            server.StartInfo = psi;
            server.EnableRaisingEvents = true;
            server.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e)
            {
                if (!String.IsNullOrEmpty(e.Data)) WriteLog("OUT " + e.Data);
            };
            server.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e)
            {
                if (!String.IsNullOrEmpty(e.Data)) WriteLog("ERR " + e.Data);
            };

            WriteLog("Starting Streamlit on port " + port + ". Data: " + dataDir);
            if (!server.Start())
            {
                Fail("PetroLab server could not be started.");
                return;
            }
            server.BeginOutputReadLine();
            server.BeginErrorReadLine();

            bool healthy = false;
            for (int attempt = 0; attempt < 120; attempt++)
            {
                if (server.HasExited)
                {
                    WriteLog("Server exited before health check. Exit code: " + server.ExitCode);
                    break;
                }
                if (IsHealthy(port))
                {
                    healthy = true;
                    break;
                }
                Thread.Sleep(500);
            }

            if (!healthy)
            {
                try { if (!server.HasExited) server.Kill(); } catch { }
                Fail("PetroLab did not finish starting. The launcher log contains the error details.");
                return;
            }

            File.WriteAllText(stateFile, server.Id + "|" + port, Encoding.ASCII);
            WriteLog("Server healthy. PID " + server.Id + ", port " + port + ".");
            OpenBrowser(port);

            server.WaitForExit();
            WriteLog("Server exited. Exit code: " + server.ExitCode);
            RemoveStateIfOwned(stateFile, server.Id);
        }
        catch (Exception ex)
        {
            WriteLog("FATAL " + ex);
            Fail("PetroLab could not start: " + ex.Message);
        }
        finally
        {
            if (ownsMutex && launchMutex != null)
            {
                try { launchMutex.ReleaseMutex(); } catch { }
            }
            if (launchMutex != null) launchMutex.Dispose();
        }
    }

    private static bool TryExistingServer(string stateFile, out int port)
    {
        port = 0;
        if (!File.Exists(stateFile)) return false;
        try
        {
            string[] parts = File.ReadAllText(stateFile).Trim().Split('|');
            if (parts.Length != 2) throw new InvalidDataException("Invalid launcher state.");
            int pid = Int32.Parse(parts[0]);
            int candidatePort = Int32.Parse(parts[1]);
            Process process = Process.GetProcessById(pid);
            if (process.HasExited || !IsHealthy(candidatePort))
            {
                File.Delete(stateFile);
                return false;
            }
            port = candidatePort;
            return true;
        }
        catch
        {
            try { File.Delete(stateFile); } catch { }
            return false;
        }
    }

    private static int FindFreePort()
    {
        TcpListener listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        int port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }

    private static bool IsHealthy(int port)
    {
        try
        {
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/_stcore/health");
            request.Timeout = 700;
            request.ReadWriteTimeout = 700;
            request.Proxy = null;
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
            {
                return response.StatusCode == HttpStatusCode.OK;
            }
        }
        catch
        {
            return false;
        }
    }

    private static void OpenBrowser(int port)
    {
        if (String.Equals(Environment.GetEnvironmentVariable("PETROLAB_LAUNCHER_NO_BROWSER"), "1", StringComparison.Ordinal))
        {
            WriteLog("Browser opening suppressed by PETROLAB_LAUNCHER_NO_BROWSER.");
            return;
        }
        string url = "http://127.0.0.1:" + port + "/";
        try
        {
            ProcessStartInfo browser = new ProcessStartInfo();
            browser.FileName = url;
            browser.UseShellExecute = true;
            Process.Start(browser);
            WriteLog("Opened browser: " + url);
        }
        catch (Exception ex)
        {
            WriteLog("Browser open failed: " + ex.Message);
            MessageBox.Show(
                "PetroLab is running, but Windows could not open the browser automatically.\n\nOpen this address manually:\n" + url,
                "PetroLab",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
        }
    }

    private static void RemoveStateIfOwned(string stateFile, int pid)
    {
        try
        {
            if (!File.Exists(stateFile)) return;
            string text = File.ReadAllText(stateFile).Trim();
            if (text.StartsWith(pid + "|", StringComparison.Ordinal)) File.Delete(stateFile);
        }
        catch { }
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static void Fail(string message)
    {
        WriteLog("FAIL " + message);
        string suffix = String.IsNullOrWhiteSpace(LogFile) ? "" : "\n\nLog: " + LogFile;
        MessageBox.Show(message + suffix, "PetroLab", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }

    private static void WriteLog(string text)
    {
        try
        {
            lock (LogSync)
            {
                if (String.IsNullOrWhiteSpace(LogFile)) return;
                File.AppendAllText(LogFile, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + text + Environment.NewLine, Encoding.UTF8);
            }
        }
        catch { }
    }
}
