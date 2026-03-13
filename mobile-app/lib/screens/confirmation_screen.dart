import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Shown after successful report submission.
/// Displays the one-time tracking code the reporter must save.
class ConfirmationScreen extends StatefulWidget {
  const ConfirmationScreen({super.key});

  @override
  State<ConfirmationScreen> createState() => _ConfirmationScreenState();
}

class _ConfirmationScreenState extends State<ConfirmationScreen> {
  bool _codeCopied = false;
  bool _codeSaved = false;

  void _copyCode(String code) {
    Clipboard.setData(ClipboardData(text: code));
    setState(() => _codeCopied = true);
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _codeCopied = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    final args = ModalRoute.of(context)?.settings.arguments;
    final Map<String, String> data = args is Map<String, String>
        ? args
        : {'report_id': args?.toString() ?? '', 'tracking_code': ''};

    final reportId = data['report_id'] ?? '';
    final trackingCode = data['tracking_code'] ?? '';
    final hasCode = trackingCode.isNotEmpty;

    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            children: [
              const SizedBox(height: 24),

              // Success icon
              Container(
                width: 80,
                height: 80,
                decoration: BoxDecoration(
                  color: Colors.green.withOpacity(0.1),
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.green, width: 2),
                ),
                child: const Icon(Icons.check, color: Colors.green, size: 40),
              ),

              const SizedBox(height: 24),

              const Text(
                'Report Received!',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 26,
                  fontWeight: FontWeight.w700,
                ),
              ),

              const SizedBox(height: 8),

              Text(
                'Your report has been received anonymously.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white.withOpacity(0.6),
                  fontSize: 14,
                ),
              ),

              const SizedBox(height: 32),

              // ── Tracking Code Card ──────────────────────────────────────
              if (hasCode) ...[
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        const Color(0xFF1A73E8).withOpacity(0.15),
                        const Color(0xFF7C3AED).withOpacity(0.15),
                      ],
                    ),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(
                      color: const Color(0xFF1A73E8).withOpacity(0.4),
                      width: 1.5,
                    ),
                  ),
                  child: Column(
                    children: [
                      Row(
                        children: [
                          const Icon(Icons.vpn_key, color: Color(0xFF60A5FA), size: 18),
                          const SizedBox(width: 8),
                          const Text(
                            'Your Tracking Code',
                            style: TextStyle(
                              color: Color(0xFF60A5FA),
                              fontWeight: FontWeight.w700,
                              fontSize: 13,
                            ),
                          ),
                          const Spacer(),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                            decoration: BoxDecoration(
                              color: Colors.amber.withOpacity(0.15),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(color: Colors.amber.withOpacity(0.4)),
                            ),
                            child: const Text(
                              'SAVE THIS',
                              style: TextStyle(
                                color: Colors.amber,
                                fontSize: 10,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                        ],
                      ),

                      const SizedBox(height: 16),

                      // The code itself
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                        decoration: BoxDecoration(
                          color: const Color(0xFF0F172A),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: Colors.white.withOpacity(0.1)),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              trackingCode,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 24,
                                fontWeight: FontWeight.w800,
                                fontFamily: 'monospace',
                                letterSpacing: 2,
                              ),
                            ),
                            const SizedBox(width: 12),
                            GestureDetector(
                              onTap: () => _copyCode(trackingCode),
                              child: AnimatedSwitcher(
                                duration: const Duration(milliseconds: 200),
                                child: _codeCopied
                                    ? const Icon(Icons.check_circle, color: Colors.green, size: 22, key: ValueKey('copied'))
                                    : const Icon(Icons.copy, color: Color(0xFF94A3B8), size: 22, key: ValueKey('copy')),
                              ),
                            ),
                          ],
                        ),
                      ),

                      const SizedBox(height: 16),

                      // Warning
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.amber.withOpacity(0.08),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: Colors.amber.withOpacity(0.2)),
                        ),
                        child: const Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(Icons.warning_amber, color: Colors.amber, size: 16),
                            SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                'This code will NOT be shown again. Save it now to check your report status and communicate with analysts.',
                                style: TextStyle(
                                  color: Colors.amber,
                                  fontSize: 12,
                                  height: 1.4,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),

                      const SizedBox(height: 12),

                      // Copy button
                      SizedBox(
                        width: double.infinity,
                        child: ElevatedButton.icon(
                          onPressed: () => _copyCode(trackingCode),
                          icon: Icon(
                            _codeCopied ? Icons.check : Icons.copy,
                            size: 16,
                          ),
                          label: Text(_codeCopied ? 'Copied!' : 'Copy Code'),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: _codeCopied
                                ? Colors.green.withOpacity(0.2)
                                : const Color(0xFF1A73E8).withOpacity(0.2),
                            foregroundColor: _codeCopied ? Colors.green : const Color(0xFF60A5FA),
                            side: BorderSide(
                              color: _codeCopied
                                  ? Colors.green.withOpacity(0.4)
                                  : const Color(0xFF1A73E8).withOpacity(0.4),
                            ),
                            elevation: 0,
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 16),

                // "I saved my code" checkbox
                GestureDetector(
                  onTap: () => setState(() => _codeSaved = !_codeSaved),
                  child: Row(
                    children: [
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        width: 22,
                        height: 22,
                        decoration: BoxDecoration(
                          color: _codeSaved
                              ? const Color(0xFF1A73E8)
                              : Colors.transparent,
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(
                            color: _codeSaved
                                ? const Color(0xFF1A73E8)
                                : Colors.white.withOpacity(0.3),
                          ),
                        ),
                        child: _codeSaved
                            ? const Icon(Icons.check, color: Colors.white, size: 14)
                            : null,
                      ),
                      const SizedBox(width: 10),
                      Text(
                        'I have saved my tracking code',
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.7),
                          fontSize: 13,
                        ),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 24),
              ],

              // ── What happens next ──────────────────────────────────────
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.04),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: Colors.white.withOpacity(0.08)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'What happens next',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                        fontSize: 13,
                      ),
                    ),
                    const SizedBox(height: 12),
                    _NextStep(step: '1', text: 'AI analysis classifies your report'),
                    _NextStep(step: '2', text: 'Pattern matching detects related reports'),
                    _NextStep(step: '3', text: 'Urgency assessed and flagged if critical'),
                    _NextStep(step: '4', text: 'Analyst may contact you via your tracking code'),
                  ],
                ),
              ),

              const SizedBox(height: 16),

              // Privacy badge
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Colors.green.withOpacity(0.08),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.green.withOpacity(0.2)),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.verified_user, color: Colors.green, size: 18),
                    SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'Your identity was never stored. This report cannot be traced back to you.',
                        style: TextStyle(color: Colors.green, fontSize: 12, height: 1.4),
                      ),
                    ),
                  ],
                ),
              ),

              if (reportId.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text(
                  'Ref: ${reportId.length >= 8 ? reportId.substring(0, 8).toUpperCase() : reportId.toUpperCase()}',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.3),
                    fontSize: 11,
                    fontFamily: 'monospace',
                  ),
                ),
              ],

              const SizedBox(height: 32),

              // Action buttons
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => Navigator.pushReplacementNamed(context, '/submit'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.white,
                        side: BorderSide(color: Colors.white.withOpacity(0.2)),
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                      ),
                      child: const Text('New Report'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: ElevatedButton(
                      onPressed: (!hasCode || _codeSaved || _codeCopied)
                          ? () => Navigator.pushReplacementNamed(context, '/home')
                          : null,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF1A73E8),
                        foregroundColor: Colors.white,
                        disabledBackgroundColor: Colors.grey.withOpacity(0.2),
                        disabledForegroundColor: Colors.grey,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                      ),
                      child: const Text('Done'),
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 8),

              if (hasCode && !_codeSaved && !_codeCopied)
                Text(
                  'Please copy or confirm you saved your code first',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.amber.withOpacity(0.7),
                    fontSize: 11,
                  ),
                ),

              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }
}

class _NextStep extends StatelessWidget {
  final String step;
  final String text;
  const _NextStep({required this.step, required this.text});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Container(
            width: 22,
            height: 22,
            decoration: BoxDecoration(
              color: const Color(0xFF1A73E8).withOpacity(0.15),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Text(
                step,
                style: const TextStyle(
                  color: Color(0xFF1A73E8),
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: TextStyle(color: Colors.white.withOpacity(0.7), fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }
}