"""CLI commands for nanobot."""

import asyncio
import os
import select
import signal
import sys
from pathlib import Path

# Force UTF-8 encoding for Windows console
if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        os.environ["PYTHONIOENCODING"] = "utf-8"
        # Re-open stdout/stderr with UTF-8 encoding
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from nanobot import __logo__, __version__
from nanobot.config.paths import get_workspace_path
from nanobot.config.schema import Config
from nanobot.utils.helpers import sync_workspace_templates

app = typer.Typer(
    name="nanobot",
    help=f"{__logo__} nanobot - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}

# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios
        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    # Save terminal state so we can restore it on exit
    try:
        import termios
        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    from nanobot.config.paths import get_cli_history_path

    history_file = get_cli_history_path()
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,   # Enter submits (single line mode)
    )


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Render assistant response with consistent terminal styling."""
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"[cyan]{__logo__} nanobot[/cyan]")
    console.print(body)
    console.print()


def _is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    """Read user input using prompt_toolkit (handles paste, history, display).

    prompt_toolkit natively handles:
    - Multiline paste (bracketed paste mode)
    - History navigation (up/down arrows)
    - Clean display (no ghost characters or artifacts)
    """
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc



def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} nanobot v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """nanobot - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard():
    """Initialize nanobot configuration and workspace."""
    from nanobot.config.loader import get_config_path, load_config, save_config
    from nanobot.config.schema import AgentDefaults, Config

    config_path = get_config_path()
    main_workspace = str(Path.home() / ".nanobot" / "workspace" / "main")

    if config_path.exists():
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        console.print("  [bold]y[/bold] = overwrite with defaults (existing values will be lost)")
        console.print("  [bold]N[/bold] = refresh config, keeping existing values and adding new fields")
        if typer.confirm("Overwrite?"):
            config = Config()
            config.agents.instances["main"] = AgentDefaults(
                workspace=main_workspace,
            )
            save_config(config)
            console.print(f"[green]✓[/green] Config reset to defaults at {config_path}")
        else:
            config = load_config()
            # Ensure at least the 'main' instance exists after refresh
            if "main" not in config.agents.instances:
                config.agents.instances["main"] = AgentDefaults(
                    workspace=main_workspace,
                )
            save_config(config)
            console.print(f"[green]✓[/green] Config refreshed at {config_path} (existing values preserved)")
    else:
        config = Config()
        config.agents.instances["main"] = AgentDefaults(
            workspace=main_workspace,
        )
        save_config(config)
        console.print(f"[green]✓[/green] Created config at {config_path}")

    # Sync templates to the main workspace
    workspace = Path(main_workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    sync_workspace_templates(workspace)
    console.print(f"[green]✓[/green] Initialized workspace at {workspace}")

    console.print(f"\n{__logo__} nanobot is ready!")
    console.print("\nNext steps:")
    console.print("  1. Add your API key to [cyan]~/.nanobot/config.json[/cyan]")
    console.print("     Get one at: https://openrouter.ai/keys")
    console.print("  2. Chat: [cyan]nanobot agent -m \"Hello!\"[/cyan]")
    console.print("  3. New agent: [cyan]nanobot agent-create <name>[/cyan]")
    console.print("\n[dim]Want Telegram/WhatsApp? See: https://github.com/HKUDS/nanobot#-chat-apps[/dim]")






def _make_provider(config: Config):
    """Create the appropriate LLM provider from config."""
    from nanobot.providers.openai_codex_provider import OpenAICodexProvider
    from nanobot.providers.azure_openai_provider import AzureOpenAIProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    # OpenAI Codex (OAuth)
    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        return OpenAICodexProvider(default_model=model)

    # Custom: direct OpenAI-compatible endpoint, bypasses LiteLLM
    from nanobot.providers.custom_provider import CustomProvider
    if provider_name == "custom":
        return CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
        )

    # Azure OpenAI: direct Azure OpenAI endpoint with deployment name
    if provider_name == "azure_openai":
        if not p or not p.api_key or not p.api_base:
            console.print("[red]Error: Azure OpenAI requires api_key and api_base.[/red]")
            console.print("Set them in ~/.nanobot/config.json under providers.azure_openai section")
            console.print("Use the model field to specify the deployment name.")
            raise typer.Exit(1)
        
        return AzureOpenAIProvider(
            api_key=p.api_key,
            api_base=p.api_base,
            default_model=model,
        )

    from nanobot.providers.litellm_provider import LiteLLMProvider
    from nanobot.providers.registry import find_by_name
    spec = find_by_name(provider_name)
    if not model.startswith("bedrock/") and not (p and p.api_key) and not (spec and spec.is_oauth):
        console.print("[red]Error: No API key configured.[/red]")
        console.print("Set one in ~/.nanobot/config.json under providers section")
        raise typer.Exit(1)

    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=provider_name,
    )


def _load_runtime_config(config: str | None = None, workspace: str | None = None) -> Config:
    """Load config and optionally override the active workspace."""
    from nanobot.config.loader import load_config, set_config_path

    config_path = None
    if config:
        config_path = Path(config).expanduser().resolve()
        if not config_path.exists():
            console.print(f"[red]Error: Config file not found: {config_path}[/red]")
            raise typer.Exit(1)
        set_config_path(config_path)
        console.print(f"[dim]Using config: {config_path}[/dim]")

    loaded = load_config(config_path)
    if workspace:
        loaded.agents.defaults.workspace = workspace
    return loaded


# ============================================================================
# Gateway / Server
# ============================================================================


@app.command()
def gateway(
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Start the nanobot gateway."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.channels.manager import ChannelManager
    from nanobot.config.paths import get_cron_dir
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronJob
    from nanobot.heartbeat.service import HeartbeatService
    from nanobot.session.manager import SessionManager

    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    config = _load_runtime_config(config, workspace)

    console.print(f"{__logo__} Starting nanobot gateway on port {port}...")
    
    instances = config.agents.instances
    if not instances:
        instances = {"main": config.agents.defaults}

    main_bus = MessageBus()
    provider = _make_provider(config)
    
    agents = []
    crons = []
    heartbeats = []
    forward_coros = []
    
    channels = ChannelManager(config, main_bus)
    
    # Pre-allocate message buses and parse profiles for all instances
    # Profile is auto-derived from <workspace>/PROFILE.md (convention over config)
    all_buses = {}
    peer_profiles = {}
    for idx, (instance_name, cfg) in enumerate(instances.items()):
        is_primary = (instance_name == "main") or (idx == 0 and not instances.get("main"))
        all_buses[instance_name] = main_bus if is_primary else MessageBus()
        profile_path = Path(cfg.workspace).expanduser() / "PROFILE.md"
        if profile_path.exists():
            peer_profiles[instance_name] = profile_path.read_text(encoding="utf-8")
        else:
            peer_profiles[instance_name] = "No description available."

    for instance_name, agent_config in instances.items():
        bus = all_buses[instance_name]
        is_primary = bus is main_bus
        peer_buses = {k: v for k, v in all_buses.items() if k != instance_name}
        peer_profiles_filtered = {k: v for k, v in peer_profiles.items() if k != instance_name}

        instance_workspace = Path(agent_config.workspace).expanduser()
        sync_workspace_templates(instance_workspace)
        session_manager = SessionManager(instance_workspace)
        
        if not is_primary:
            # "system" is an internal pseudo-channel used for peer-to-peer delegation.
            # Outbound messages targeting it from secondary agents are internal artifacts
            # (e.g. from the message tool echoing back during a delegated task) and
            # should be silently dropped - the real result is routed via delegated_from.
            _INTERNAL_CHANNELS = {"system"}
            def _make_forward(b, name):
                async def _forward():
                    while True:
                        try:
                            msg = await b.consume_outbound()
                            if msg.metadata and msg.metadata.get("delegated_from"):
                                caller = msg.metadata["delegated_from"]
                                target_bus = all_buses.get(caller, main_bus)
                                from nanobot.bus.events import InboundMessage
                                await target_bus.publish_inbound(InboundMessage(
                                    channel="system",
                                    sender_id=f"peer:{name}",
                                    chat_id=msg.chat_id,
                                    content=f"Peer agent '{name}' finished its task. Result:\n{msg.content}"
                                ))
                            elif msg.channel not in _INTERNAL_CHANNELS:
                                # Forward proactive notifications to main outbound (real channels only)
                                msg.content = f"[{name}] {msg.content}"
                                await main_bus.publish_outbound(msg)
                            # else: silently drop internal pseudo-channel messages
                        except asyncio.CancelledError:
                            break
                        except Exception:
                            await asyncio.sleep(1)
                return _forward
            forward_coros.append(_make_forward(bus, instance_name))
            
        cron_store_path = instance_workspace / "cron" / "jobs.json"
        cron_store_path.parent.mkdir(parents=True, exist_ok=True)
        cron = CronService(cron_store_path, agent_name=instance_name)
        
        agent = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=instance_workspace,
            model=agent_config.model,
            temperature=agent_config.temperature,
            max_tokens=agent_config.max_tokens,
            max_iterations=agent_config.max_tool_iterations,
            memory_window=agent_config.memory_window,
            reasoning_effort=agent_config.reasoning_effort,
            brave_api_key=config.tools.web.search.api_key or None,
            web_proxy=config.tools.web.proxy or None,
            exec_config=config.tools.exec,
            cron_service=cron,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            session_manager=session_manager,
            mcp_servers=config.tools.mcp_servers,
            channels_config=config.channels,
            peer_buses=peer_buses,
            peer_profiles=peer_profiles_filtered,
            allowed_agent_delegates=agent_config.allowed_agent_delegates,
            self_agent_name=instance_name,
        )
        
        def _make_cron_callback(a: AgentLoop, c: CronService):
            async def on_cron_job(job: CronJob) -> str | None:
                from nanobot.agent.tools.cron import CronTool
                from nanobot.agent.tools.message import MessageTool
                reminder_note = (
                    "[Scheduled Task] Timer finished.\n\n"
                    f"Task '{job.name}' has been triggered.\n"
                    f"Scheduled instruction: {job.payload.message}"
                )
                cron_tool = a.tools.get("cron")
                cron_token = None
                if isinstance(cron_tool, CronTool):
                    cron_token = cron_tool.set_cron_context(True)
                try:
                    response = await a.process_direct(
                        reminder_note,
                        session_key=f"cron:{job.id}",
                        channel=job.payload.channel or "cli",
                        chat_id=job.payload.to or "direct",
                    )
                finally:
                    if isinstance(cron_tool, CronTool) and cron_token is not None:
                        cron_tool.reset_cron_context(cron_token)
                message_tool = a.tools.get("message")
                if isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
                    return response
                if job.payload.deliver and job.payload.to and response:
                    from nanobot.bus.events import OutboundMessage
                    await main_bus.publish_outbound(OutboundMessage(
                        channel=job.payload.channel or "cli",
                        chat_id=job.payload.to,
                        content=response
                    ))
                return response
            return on_cron_job
            
        cron.on_job = _make_cron_callback(agent, cron)
        
        def _make_heartbeat_callbacks(a: AgentLoop, sm: SessionManager):
            def _pick_heartbeat_target() -> tuple[str, str]:
                enabled = set(channels.enabled_channels)
                for item in sm.list_sessions():
                    key = item.get("key") or ""
                    if ":" not in key:
                        continue
                    channel, chat_id = key.split(":", 1)
                    if channel in {"cli", "system"}:
                        continue
                    if channel in enabled and chat_id:
                        return channel, chat_id
                return "cli", "direct"

            async def on_heartbeat_execute(tasks: str) -> str:
                channel, chat_id = _pick_heartbeat_target()
                async def _silent(*_args, **_kwargs): pass
                return await a.process_direct(
                    tasks,
                    session_key="heartbeat",
                    channel=channel,
                    chat_id=chat_id,
                    on_progress=_silent,
                )

            async def on_heartbeat_notify(response: str) -> None:
                from nanobot.bus.events import OutboundMessage
                channel, chat_id = _pick_heartbeat_target()
                if channel == "cli": return
                await main_bus.publish_outbound(OutboundMessage(channel=channel, chat_id=chat_id, content=response))
            
            return on_heartbeat_execute, on_heartbeat_notify
            
        on_hb_exec, on_hb_notify = _make_heartbeat_callbacks(agent, session_manager)
            
        hb_cfg = config.gateway.heartbeat
        heartbeat = HeartbeatService(
            workspace=instance_workspace,
            provider=provider,
            model=agent.model,
            on_execute=on_hb_exec,
            on_notify=on_hb_notify,
            interval_s=hb_cfg.interval_s,
            enabled=hb_cfg.enabled,
            agent_name=instance_name,
        )
        
        agents.append(agent)
        crons.append(cron)
        heartbeats.append(heartbeat)

    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")

    total_cron_jobs = sum(c.status()["jobs"] for c in crons)
    if total_cron_jobs > 0:
        console.print(f"[green]✓[/green] Cron: {total_cron_jobs} scheduled jobs across {len(crons)} agents")

    console.print(f"[green]✓[/green] Heartbeat: every {config.gateway.heartbeat.interval_s}s for {len(heartbeats)} agents")

    async def run():
        tasks = []
        try:
            for c in crons:
                await c.start()
            for h in heartbeats:
                await h.start()
                
            coroutines = [a.run() for a in agents] + [channels.start_all()] + [f() for f in forward_coros]
            gather_task = asyncio.gather(*coroutines)
            tasks.append(gather_task)
            await gather_task
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        finally:
            for t in tasks:
                t.cancel()
            for a in agents:
                await a.close_mcp()
            for h in heartbeats:
                h.stop()
            for c in crons:
                c.stop()
            for a in agents:
                a.stop()
            await channels.stop_all()

    asyncio.run(run())




# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file path"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown", help="Render assistant output as Markdown"),
    logs: bool = typer.Option(False, "--logs/--no-logs", help="Show nanobot runtime logs during chat"),
):
    """Interact with the agent directly."""
    from loguru import logger

    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.config.paths import get_cron_dir
    from nanobot.cron.service import CronService

    config = _load_runtime_config(config, workspace)
    sync_workspace_templates(config.workspace_path)

    bus = MessageBus()
    provider = _make_provider(config)

    # Create cron service for tool usage (no callback needed for CLI unless running)
    cron_store_path = get_cron_dir() / "jobs.json"
    cron = CronService(cron_store_path)

    if logs:
        logger.enable("nanobot")
    else:
        logger.disable("nanobot")

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        brave_api_key=config.tools.web.search.api_key or None,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
    )

    # Show spinner when logs are off (no output to miss); skip when logs are on
    def _thinking_ctx():
        if logs:
            from contextlib import nullcontext
            return nullcontext()
        # Animated spinner is safe to use with prompt_toolkit input handling
        return console.status("[dim]nanobot is thinking...[/dim]", spinner="dots")

    async def _cli_progress(content: str, *, tool_hint: bool = False) -> None:
        ch = agent_loop.channels_config
        if ch and tool_hint and not ch.send_tool_hints:
            return
        if ch and not tool_hint and not ch.send_progress:
            return
        console.print(f"  [dim]↳ {content}[/dim]")

    if message:
        # Single message mode — direct call, no bus needed
        async def run_once():
            with _thinking_ctx():
                response = await agent_loop.process_direct(message, session_id, on_progress=_cli_progress)
            _print_agent_response(response, render_markdown=markdown)
            await agent_loop.close_mcp()

        asyncio.run(run_once())
    else:
        # Interactive mode — route through bus like other channels
        from nanobot.bus.events import InboundMessage
        _init_prompt_session()
        console.print(f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n")

        if ":" in session_id:
            cli_channel, cli_chat_id = session_id.split(":", 1)
        else:
            cli_channel, cli_chat_id = "cli", session_id

        def _handle_signal(signum, frame):
            sig_name = signal.Signals(signum).name
            _restore_terminal()
            console.print(f"\nReceived {sig_name}, goodbye!")
            sys.exit(0)

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
        # SIGHUP is not available on Windows
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, _handle_signal)
        # Ignore SIGPIPE to prevent silent process termination when writing to closed pipes
        # SIGPIPE is not available on Windows
        if hasattr(signal, 'SIGPIPE'):
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)

        async def run_interactive():
            bus_task = asyncio.create_task(agent_loop.run())
            turn_done = asyncio.Event()
            turn_done.set()
            turn_response: list[str] = []

            async def _consume_outbound():
                while True:
                    try:
                        msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
                        if msg.metadata.get("_progress"):
                            is_tool_hint = msg.metadata.get("_tool_hint", False)
                            ch = agent_loop.channels_config
                            if ch and is_tool_hint and not ch.send_tool_hints:
                                pass
                            elif ch and not is_tool_hint and not ch.send_progress:
                                pass
                            else:
                                console.print(f"  [dim]↳ {msg.content}[/dim]")
                        elif not turn_done.is_set():
                            if msg.content:
                                turn_response.append(msg.content)
                            turn_done.set()
                        elif msg.content:
                            console.print()
                            _print_agent_response(msg.content, render_markdown=markdown)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

            outbound_task = asyncio.create_task(_consume_outbound())

            try:
                while True:
                    try:
                        _flush_pending_tty_input()
                        user_input = await _read_interactive_input_async()
                        command = user_input.strip()
                        if not command:
                            continue

                        if _is_exit_command(command):
                            _restore_terminal()
                            console.print("\nGoodbye!")
                            break

                        turn_done.clear()
                        turn_response.clear()

                        await bus.publish_inbound(InboundMessage(
                            channel=cli_channel,
                            sender_id="user",
                            chat_id=cli_chat_id,
                            content=user_input,
                        ))

                        with _thinking_ctx():
                            await turn_done.wait()

                        if turn_response:
                            _print_agent_response(turn_response[0], render_markdown=markdown)
                    except KeyboardInterrupt:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
                    except EOFError:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
            finally:
                agent_loop.stop()
                outbound_task.cancel()
                await asyncio.gather(bus_task, outbound_task, return_exceptions=True)
                await agent_loop.close_mcp()

        asyncio.run(run_interactive())


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from nanobot.config.loader import load_config

    config = load_config()

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Configuration", style="yellow")

    # WhatsApp
    wa = config.channels.whatsapp
    table.add_row(
        "WhatsApp",
        "✓" if wa.enabled else "✗",
        wa.bridge_url
    )

    dc = config.channels.discord
    table.add_row(
        "Discord",
        "✓" if dc.enabled else "✗",
        dc.gateway_url
    )

    # Feishu
    fs = config.channels.feishu
    fs_config = f"app_id: {fs.app_id[:10]}..." if fs.app_id else "[dim]not configured[/dim]"
    table.add_row(
        "Feishu",
        "✓" if fs.enabled else "✗",
        fs_config
    )

    # Mochat
    mc = config.channels.mochat
    mc_base = mc.base_url or "[dim]not configured[/dim]"
    table.add_row(
        "Mochat",
        "✓" if mc.enabled else "✗",
        mc_base
    )

    # Telegram
    tg = config.channels.telegram
    tg_config = f"token: {tg.token[:10]}..." if tg.token else "[dim]not configured[/dim]"
    table.add_row(
        "Telegram",
        "✓" if tg.enabled else "✗",
        tg_config
    )

    # Slack
    slack = config.channels.slack
    slack_config = "socket" if slack.app_token and slack.bot_token else "[dim]not configured[/dim]"
    table.add_row(
        "Slack",
        "✓" if slack.enabled else "✗",
        slack_config
    )

    # DingTalk
    dt = config.channels.dingtalk
    dt_config = f"client_id: {dt.client_id[:10]}..." if dt.client_id else "[dim]not configured[/dim]"
    table.add_row(
        "DingTalk",
        "✓" if dt.enabled else "✗",
        dt_config
    )

    # QQ
    qq = config.channels.qq
    qq_config = f"app_id: {qq.app_id[:10]}..." if qq.app_id else "[dim]not configured[/dim]"
    table.add_row(
        "QQ",
        "✓" if qq.enabled else "✗",
        qq_config
    )

    # Email
    em = config.channels.email
    em_config = em.imap_host if em.imap_host else "[dim]not configured[/dim]"
    table.add_row(
        "Email",
        "✓" if em.enabled else "✗",
        em_config
    )

    console.print(table)


def _get_bridge_dir() -> Path:
    """Get the bridge directory, setting it up if needed."""
    import shutil
    import subprocess

    # User's bridge location
    from nanobot.config.paths import get_bridge_install_dir

    user_bridge = get_bridge_install_dir()

    # Check if already built
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge

    # Check for npm
    if not shutil.which("npm"):
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)

    # Find source bridge: first check package data, then source dir
    pkg_bridge = Path(__file__).parent.parent / "bridge"  # nanobot/bridge (installed)
    src_bridge = Path(__file__).parent.parent.parent / "bridge"  # repo root/bridge (dev)

    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge

    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall nanobot")
        raise typer.Exit(1)

    console.print(f"{__logo__} Setting up bridge...")

    # Copy to user directory
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))

    # Install and build
    try:
        console.print("  Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=user_bridge, check=True, capture_output=True)

        console.print("  Building...")
        subprocess.run(["npm", "run", "build"], cwd=user_bridge, check=True, capture_output=True)

        console.print("[green]✓[/green] Bridge ready\n")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Build failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
        raise typer.Exit(1)

    return user_bridge


@channels_app.command("login")
def channels_login():
    """Link device via QR code."""
    import subprocess

    from nanobot.config.loader import load_config
    from nanobot.config.paths import get_runtime_subdir

    config = load_config()
    bridge_dir = _get_bridge_dir()

    console.print(f"{__logo__} Starting bridge...")
    console.print("Scan the QR code to connect.\n")

    env = {**os.environ}
    if config.channels.whatsapp.bridge_token:
        env["BRIDGE_TOKEN"] = config.channels.whatsapp.bridge_token
    env["AUTH_DIR"] = str(get_runtime_subdir("whatsapp-auth"))

    try:
        subprocess.run(["npm", "start"], cwd=bridge_dir, check=True, env=env)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Bridge failed: {e}[/red]")
    except FileNotFoundError:
        console.print("[red]npm not found. Please install Node.js.[/red]")


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show nanobot status."""
    from nanobot.config.loader import get_config_path, load_config

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} nanobot Status\n")

    console.print(f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}")
    console.print(f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}")

    if config_path.exists():
        from nanobot.providers.registry import PROVIDERS

        console.print(f"Model: {config.agents.defaults.model}")

        # Check API keys from registry
        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            if p is None:
                continue
            if spec.is_oauth:
                console.print(f"{spec.label}: [green]✓ (OAuth)[/green]")
            elif spec.is_local:
                # Local deployments show api_base instead of api_key
                if p.api_base:
                    console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
                else:
                    console.print(f"{spec.label}: [dim]not set[/dim]")
            else:
                has_key = bool(p.api_key)
                console.print(f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}")


# ============================================================================
# OAuth Login
# ============================================================================

provider_app = typer.Typer(help="Manage providers")
app.add_typer(provider_app, name="provider")


_LOGIN_HANDLERS: dict[str, callable] = {}


def _register_login(name: str):
    def decorator(fn):
        _LOGIN_HANDLERS[name] = fn
        return fn
    return decorator


@provider_app.command("login")
def provider_login(
    provider: str = typer.Argument(..., help="OAuth provider (e.g. 'openai-codex', 'github-copilot')"),
):
    """Authenticate with an OAuth provider."""
    from nanobot.providers.registry import PROVIDERS

    key = provider.replace("-", "_")
    spec = next((s for s in PROVIDERS if s.name == key and s.is_oauth), None)
    if not spec:
        names = ", ".join(s.name.replace("_", "-") for s in PROVIDERS if s.is_oauth)
        console.print(f"[red]Unknown OAuth provider: {provider}[/red]  Supported: {names}")
        raise typer.Exit(1)

    handler = _LOGIN_HANDLERS.get(spec.name)
    if not handler:
        console.print(f"[red]Login not implemented for {spec.label}[/red]")
        raise typer.Exit(1)

    console.print(f"{__logo__} OAuth Login - {spec.label}\n")
    handler()


@_register_login("openai_codex")
def _login_openai_codex() -> None:
    try:
        from oauth_cli_kit import get_token, login_oauth_interactive
        token = None
        try:
            token = get_token()
        except Exception:
            pass
        if not (token and token.access):
            console.print("[cyan]Starting interactive OAuth login...[/cyan]\n")
            token = login_oauth_interactive(
                print_fn=lambda s: console.print(s),
                prompt_fn=lambda s: typer.prompt(s),
            )
        if not (token and token.access):
            console.print("[red]✗ Authentication failed[/red]")
            raise typer.Exit(1)
        console.print(f"[green]✓ Authenticated with OpenAI Codex[/green]  [dim]{token.account_id}[/dim]")
    except ImportError:
        console.print("[red]oauth_cli_kit not installed. Run: pip install oauth-cli-kit[/red]")
        raise typer.Exit(1)


@_register_login("github_copilot")
def _login_github_copilot() -> None:
    import asyncio

    console.print("[cyan]Starting GitHub Copilot device flow...[/cyan]\n")

    async def _trigger():
        from litellm import acompletion
        await acompletion(model="github_copilot/gpt-4o", messages=[{"role": "user", "content": "hi"}], max_tokens=1)

    try:
        asyncio.run(_trigger())
        console.print("[green]✓ Authenticated with GitHub Copilot[/green]")
    except Exception as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)


# ============================================================================
# Agent Management Commands
# ============================================================================
@app.command("agent-create")
def agent_create(
    name: str = typer.Argument(..., help="Name of the new agent (e.g. 'coder', 'researcher')"),
    config_path: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Create a new agent, initialize its workspace, and register it in config.json."""
    from nanobot.config.loader import get_config_path, load_config, save_config
    from nanobot.config.schema import AgentDefaults

    cfg_path = Path(config_path) if config_path else get_config_path()
    config = load_config(cfg_path) if cfg_path.exists() else None

    if config is None:
        console.print("[red]Config not found. Run [bold]nanobot onboard[/bold] first.[/red]")
        raise typer.Exit(1)

    if name in config.agents.instances:
        console.print(f"[yellow]Agent [bold]{name}[/bold] already exists in config.[/yellow]")
        raise typer.Exit(1)

    agent_workspace = Path.home() / ".nanobot" / "workspace" / name
    agent_profile = agent_workspace / "PROFILE.md"

    config.agents.instances[name] = AgentDefaults(
        workspace=str(agent_workspace),
    )
    save_config(config)
    console.print(f"[green]✓[/green] Registered agent [bold]{name}[/bold] in config")

    agent_workspace.mkdir(parents=True, exist_ok=True)
    sync_workspace_templates(agent_workspace)
    console.print(f"[green]✓[/green] Initialized workspace at {agent_workspace}")

    console.print(f"\n[bold]{__logo__} Agent [cyan]{name}[/cyan] is ready![/bold]")
    console.print("\nNext steps:")
    console.print(f"  1. Edit [cyan]{agent_workspace / 'PROFILE.md'}[/cyan] to describe the agent's capabilities")
    console.print(f"  2. Set [cyan]allowed_agent_delegates[/cyan] in config.json to control which agents can call [bold]{name}[/bold]")
    console.print("  3. Restart [cyan]nanobot gateway[/cyan] to activate the new agent")


if __name__ == "__main__":
    app()
