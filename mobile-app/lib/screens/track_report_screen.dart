import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../services/report_service.dart';
import 'package:provider/provider.dart';

/// Reporter uses their one-time tracking code to:
/// - Check report status and AI analysis result
/// - Read messages from analysts
/// - Send replies anonymously
class TrackReportScreen extends StatefulWidget {
  const TrackReportScreen({super.key});

  @override
  State<TrackReportScreen> createState() => _TrackReportScreenState();
}

class _TrackReportScreenState extends State<TrackReportScreen> {
  final _codeController = TextEditingController();
  final _messageController = TextEditingController();
  final _scrollController = ScrollController();

  bool _loading = false;
  bool _sending = false;
  String? _error;
  TrackResponse? _trackData;
  String? _activeCode;

  @override
  void dispose() {
    _codeController.dispose();
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _trackReport() async {
    final code = _codeController.text.trim().toUpperCase();
    if (code.isEmpty) return;

    setState(() { _loading = true; _error = null; _trackData = null; });

    try {
      final service = context.read<ReportService>();
      final result = await service.trackReport(code);
      setState(() {
        _trackData = result;
        _activeCode = code;
        _loading = false;
      });
      // Scroll to messages
      await Future.delayed(const Duration(milliseconds: 300));
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 400),
          curve: Curves.easeOut,
        );
      }
    } catch (e) {
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  Future<void> _sendMessage() async {
    final msg = _messageController.text.trim();
    if (msg.isEmpty || _activeCode == null) return;

    setState(() => _sending = true);
    try {
      final service = context.read<ReportService>();
      await service.sendReporterMessage(_activeCode!, msg);
      _messageController.clear();
      // Refresh to show new message
      final result = await service.trackReport(_activeCode!);
      setState(() { _trackData = result; _sending = false; });
      // Scroll to bottom
      await Future.delayed(const Duration(milliseconds: 200));
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    } catch (e) {
      setState(() => _sending = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to send: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0F172A),
        foregroundColor: Colors.white,
        title: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.track_changes, color: Color(0xFF60A5FA), size: 18),
            SizedBox(width: 8),
            Text('Track Report', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
          ],
        ),
        elevation: 0,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1),
          child: Container(height: 1, color: Colors.white.withOpacity(0.06)),
        ),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          controller: _scrollController,
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [

              // ── Code Entry Card ────────────────────────────────────────
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.04),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: Colors.white.withOpacity(0.08)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.vpn_key, color: Color(0xFF60A5FA), size: 18),
                        SizedBox(width: 8),
                        Text(
                          'Enter Your Tracking Code',
                          style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w600,
                            fontSize: 15,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Use the code you received when you submitted your report.',
                      style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 12),
                    ),
                    const SizedBox(height: 16),

                    // Code input
                    TextField(
                      controller: _codeController,
                      textCapitalization: TextCapitalization.characters,
                      style: const TextStyle(
                        color: Colors.white,
                        fontFamily: 'monospace',
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 2,
                      ),
                      decoration: InputDecoration(
                        hintText: 'KE-XXXX-XXXX',
                        hintStyle: TextStyle(
                          color: Colors.white.withOpacity(0.2),
                          fontFamily: 'monospace',
                          fontSize: 20,
                          letterSpacing: 2,
                        ),
                        filled: true,
                        fillColor: const Color(0xFF0F172A),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide(color: Colors.white.withOpacity(0.1)),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide(color: Colors.white.withOpacity(0.1)),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: Color(0xFF1A73E8)),
                        ),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                        suffixIcon: _codeController.text.isNotEmpty
                            ? IconButton(
                                icon: const Icon(Icons.clear, color: Color(0xFF64748B), size: 18),
                                onPressed: () {
                                  _codeController.clear();
                                  setState(() { _trackData = null; _error = null; });
                                },
                              )
                            : null,
                      ),
                      onChanged: (_) => setState(() {}),
                      onSubmitted: (_) => _trackReport(),
                    ),

                    const SizedBox(height: 12),

                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: _loading || _codeController.text.trim().isEmpty
                            ? null
                            : _trackReport,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF1A73E8),
                          foregroundColor: Colors.white,
                          disabledBackgroundColor: Colors.grey.withOpacity(0.15),
                          disabledForegroundColor: Colors.grey,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                        child: _loading
                            ? const SizedBox(
                                height: 18,
                                width: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Text('Check Status', style: TextStyle(fontWeight: FontWeight.w600)),
                      ),
                    ),
                  ],
                ),
              ),

              // ── Error ──────────────────────────────────────────────────
              if (_error != null) ...[
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.red.withOpacity(0.08),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.red.withOpacity(0.2)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline, color: Colors.red, size: 18),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          _error == 'Tracking code not found'
                              ? 'Code not found. Please check you entered it correctly.'
                              : _error!,
                          style: const TextStyle(color: Colors.red, fontSize: 13),
                        ),
                      ),
                    ],
                  ),
                ),
              ],

              // ── Report Status ──────────────────────────────────────────
              if (_trackData != null) ...[
                const SizedBox(height: 24),

                // Status card
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.04),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(
                      color: _statusColor(_trackData!.status).withOpacity(0.3),
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          _StatusChip(status: _trackData!.status),
                          const Spacer(),
                          if (_trackData!.urgencyLevel != null)
                            _UrgencyChip(level: _trackData!.urgencyLevel!),
                        ],
                      ),
                      const SizedBox(height: 14),
                      _InfoRow(
                        icon: Icons.category_outlined,
                        label: 'Category',
                        value: (_trackData!.category ?? _trackData!.userCategory ?? 'Unknown')
                            .replaceAll('_', ' ')
                            .toUpperCase(),
                      ),
                      const SizedBox(height: 8),
                      _InfoRow(
                        icon: Icons.access_time,
                        label: 'Submitted',
                        value: _formatDate(_trackData!.submittedAt),
                      ),
                      const SizedBox(height: 8),
                      _InfoRow(
                        icon: Icons.info_outline,
                        label: 'Status',
                        value: _statusLabel(_trackData!.status),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 24),

                // ── Messages ────────────────────────────────────────────
                Row(
                  children: [
                    const Icon(Icons.chat_bubble_outline, color: Color(0xFF60A5FA), size: 16),
                    const SizedBox(width: 8),
                    const Text(
                      'Messages',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                        fontSize: 15,
                      ),
                    ),
                    if (_trackData!.unreadFromAnalyst > 0) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1A73E8),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(
                          '${_trackData!.unreadFromAnalyst} new',
                          style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w700),
                        ),
                      ),
                    ],
                    const Spacer(),
                    TextButton.icon(
                      onPressed: _trackReport,
                      icon: const Icon(Icons.refresh, size: 14),
                      label: const Text('Refresh', style: TextStyle(fontSize: 12)),
                      style: TextButton.styleFrom(foregroundColor: const Color(0xFF64748B)),
                    ),
                  ],
                ),

                const SizedBox(height: 10),

                // Messages list
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: const Color(0xFF0F172A),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: Colors.white.withOpacity(0.07)),
                  ),
                  child: Column(
                    children: [
                      if (_trackData!.messages.isEmpty)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 24),
                          child: Column(
                            children: [
                              Icon(Icons.chat_bubble_outline,
                                  color: Colors.white.withOpacity(0.2), size: 32),
                              const SizedBox(height: 10),
                              Text(
                                'No messages yet.\nAn analyst may reach out with follow-up questions.',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  color: Colors.white.withOpacity(0.35),
                                  fontSize: 13,
                                  height: 1.5,
                                ),
                              ),
                            ],
                          ),
                        )
                      else
                        ...(_trackData!.messages.map((msg) => _MessageBubble(message: msg))),
                    ],
                  ),
                ),

                const SizedBox(height: 14),

                // Reply input
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.04),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: Colors.white.withOpacity(0.08)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Send a message to the analyst',
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.5),
                          fontSize: 11,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _messageController,
                              style: const TextStyle(color: Colors.white, fontSize: 14),
                              maxLines: 3,
                              minLines: 1,
                              decoration: InputDecoration(
                                hintText: 'Add more details or respond to analyst...',
                                hintStyle: TextStyle(color: Colors.white.withOpacity(0.25), fontSize: 13),
                                filled: true,
                                fillColor: const Color(0xFF0F172A),
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(10),
                                  borderSide: BorderSide(color: Colors.white.withOpacity(0.08)),
                                ),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(10),
                                  borderSide: BorderSide(color: Colors.white.withOpacity(0.08)),
                                ),
                                focusedBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(10),
                                  borderSide: const BorderSide(color: Color(0xFF1A73E8)),
                                ),
                                contentPadding: const EdgeInsets.all(12),
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          GestureDetector(
                            onTap: _sending ? null : _sendMessage,
                            child: Container(
                              width: 44,
                              height: 44,
                              decoration: BoxDecoration(
                                color: _sending
                                    ? Colors.grey.withOpacity(0.2)
                                    : const Color(0xFF1A73E8),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: _sending
                                  ? const Padding(
                                      padding: EdgeInsets.all(10),
                                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                    )
                                  : const Icon(Icons.send_rounded, color: Colors.white, size: 20),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 20),

                // Privacy note
                Center(
                  child: Text(
                    '🔒 Your identity remains anonymous. Only your code links you to this report.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.3),
                      fontSize: 11,
                      height: 1.5,
                    ),
                  ),
                ),

                const SizedBox(height: 32),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'analyzed': return Colors.green;
      case 'processing': return const Color(0xFF60A5FA);
      case 'flagged': return Colors.red;
      default: return Colors.amber;
    }
  }

  String _statusLabel(String status) {
    switch (status) {
      case 'pending': return 'Received — awaiting analysis';
      case 'processing': return 'AI is analysing your report';
      case 'analyzed': return 'Analysis complete';
      case 'flagged': return 'Flagged for immediate review';
      default: return status;
    }
  }

  String _formatDate(String iso) {
    try {
      final dt = DateTime.parse(iso).toLocal();
      return '${dt.day}/${dt.month}/${dt.year} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }
}

// ── Sub-widgets ─────────────────────────────────────────────────────────────

class _StatusChip extends StatelessWidget {
  final String status;
  const _StatusChip({required this.status});

  @override
  Widget build(BuildContext context) {
    final colors = {
      'pending': (Colors.amber, Colors.amber.withOpacity(0.15)),
      'processing': (const Color(0xFF60A5FA), const Color(0xFF60A5FA).withOpacity(0.15)),
      'analyzed': (Colors.green, Colors.green.withOpacity(0.15)),
      'flagged': (Colors.red, Colors.red.withOpacity(0.15)),
    };
    final (fg, bg) = colors[status] ?? (Colors.grey, Colors.grey.withOpacity(0.15));

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: fg.withOpacity(0.3)),
      ),
      child: Text(
        status.toUpperCase(),
        style: TextStyle(color: fg, fontSize: 11, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _UrgencyChip extends StatelessWidget {
  final String level;
  const _UrgencyChip({required this.level});

  @override
  Widget build(BuildContext context) {
    final colors = {
      'critical': Colors.red,
      'high': Colors.orange,
      'medium': Colors.amber,
      'low': Colors.green,
    };
    final color = colors[level] ?? Colors.grey;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Text(
        level.toUpperCase(),
        style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  const _InfoRow({required this.icon, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 14, color: const Color(0xFF64748B)),
        const SizedBox(width: 8),
        Text('$label: ', style: const TextStyle(color: Color(0xFF64748B), fontSize: 12)),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w500),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}

class _MessageBubble extends StatelessWidget {
  final TrackMessage message;
  const _MessageBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    final isAnalyst = message.sender == 'analyst';
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        mainAxisAlignment: isAnalyst ? MainAxisAlignment.start : MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (isAnalyst) ...[
            Container(
              width: 28,
              height: 28,
              decoration: BoxDecoration(
                color: const Color(0xFF1A73E8).withOpacity(0.15),
                shape: BoxShape.circle,
                border: Border.all(color: const Color(0xFF1A73E8).withOpacity(0.3)),
              ),
              child: const Icon(Icons.shield, color: Color(0xFF60A5FA), size: 14),
            ),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: isAnalyst
                    ? const Color(0xFF1A73E8).withOpacity(0.12)
                    : Colors.white.withOpacity(0.06),
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(14),
                  topRight: const Radius.circular(14),
                  bottomLeft: Radius.circular(isAnalyst ? 2 : 14),
                  bottomRight: Radius.circular(isAnalyst ? 14 : 2),
                ),
                border: Border.all(
                  color: isAnalyst
                      ? const Color(0xFF1A73E8).withOpacity(0.2)
                      : Colors.white.withOpacity(0.07),
                ),
              ),
              child: Column(
                crossAxisAlignment: isAnalyst ? CrossAxisAlignment.start : CrossAxisAlignment.end,
                children: [
                  Text(
                    isAnalyst ? '🔵 Analyst' : '⚪ You',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: isAnalyst ? const Color(0xFF60A5FA) : Colors.white.withOpacity(0.4),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    message.message,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.85),
                      fontSize: 13,
                      height: 1.4,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _formatTime(message.createdAt),
                    style: TextStyle(
                      fontSize: 10,
                      color: Colors.white.withOpacity(0.3),
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (!isAnalyst) const SizedBox(width: 8),
        ],
      ),
    );
  }

  String _formatTime(String iso) {
    try {
      final dt = DateTime.parse(iso).toLocal();
      return '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return '';
    }
  }
}