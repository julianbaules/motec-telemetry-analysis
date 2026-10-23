function results = t2_stability_analysis(laps, outDir)
%T2_STABILITY_ANALYSIS Yaw stability at the entry of T2, where every spin happened.
%
%   For a car following its path without sliding, the yaw rate equals the
%   rate at which the path turns:   r_path = a_y / V   (rad/s)
%   If the car yaws faster than its path, the body sideslip angle beta
%   grows: the rear is stepping out. The "yaw excess"
%       r_excess = r - r_path
%   is therefore a direct oversteer indicator, available before the
%   sideslip becomes large. This function:
%     1. computes beta, d(beta)/dt and r_excess through the T2 entry,
%     2. draws the beta / beta-rate phase plane, clean laps vs spins,
%     3. tests a simple warning rule: r_excess > 15 deg/s.
%
%   Sign convention of this export: in a right-hand corner the yaw rate is
%   positive and the lateral acceleration negative, hence the minus sign.

    g = 9.81;
    window = [180 300];                        % m, end of T1 -> T2 apex
    threshold = 15;                            % deg/s
    keep = ~strcmp({laps.status}, 'out-lap');
    laps = laps(keep);

    red = [0.816 0.231 0.231];
    blue = [0.165 0.471 0.839];

    fig = figure('Color', 'w', 'Position', [100 100 1150 450]);
    tl = tiledlayout(fig, 1, 2, 'TileSpacing', 'compact');
    title(tl, 'T2 entry: yaw stability, clean laps (blue) vs spins (red)', 'FontWeight', 'bold');
    axA = nexttile(tl); hold(axA, 'on'); grid(axA, 'on');
    axB = nexttile(tl); hold(axB, 'on'); grid(axB, 'on');

    names = strings(numel(laps), 1);
    spun = false(numel(laps), 1);
    maxExcess = zeros(numel(laps), 1);
    warnAt = nan(numel(laps), 1);
    spinAt = nan(numel(laps), 1);

    for k = 1:numel(laps)
        T = laps(k).data;
        in = T.Distance >= window(1) & T.Distance <= window(2);
        d = T.Distance(in);
        t = T.Time(in);
        V = max(T.("Chassis Velocity X")(in), 5);                   % m/s, avoid /0
        rPath = rad2deg(-T.("CG Accel Lateral")(in) * g ./ V);      % deg/s
        rExcess = T.("Chassis Yaw Rate")(in) - rPath;
        beta = T.Sideslip(in);
        betaRate = gradient(beta, t);

        names(k) = sprintf('%s L%d', laps(k).stint, laps(k).lap);
        spun(k) = any(abs(beta) > 15);
        maxExcess(k) = max(rExcess);
        iw = find(rExcess > threshold, 1);
        if ~isempty(iw), warnAt(k) = d(iw); end
        is = find(abs(beta) > 15, 1);
        if ~isempty(is), spinAt(k) = d(is); end

        c = blue; w = 1; if spun(k), c = red; w = 1.6; end
        plot(axA, d, rExcess, 'Color', c, 'LineWidth', w);
        plot(axB, beta, betaRate, 'Color', c, 'LineWidth', w);
    end

    yline(axA, threshold, '--', sprintf('warning threshold %d deg/s', threshold), ...
          'LabelHorizontalAlignment', 'left', 'Color', [0.32 0.32 0.31]);
    xlabel(axA, 'Distance (m)');
    ylabel(axA, 'Yaw excess r - a_y/V (deg/s)');
    ylim(axA, [-30 80]);
    title(axA, 'Yaw rate above what the path requires', 'FontWeight', 'normal');

    xlabel(axB, 'Body sideslip \beta (deg)');
    ylabel(axB, 'd\beta/dt (deg/s)');
    xlim(axB, [-35 10]); ylim(axB, [-80 40]);
    title(axB, 'Phase plane \beta - d\beta/dt', 'FontWeight', 'normal');
    exportgraphics(fig, fullfile(outDir, 'matlab_03_t2_stability.png'), 'Resolution', 160);

    results = table(names, spun, maxExcess, warnAt, spinAt, spinAt - warnAt, ...
        'VariableNames', {'Lap', 'Spin', 'MaxYawExcess_degps', 'WarningAt_m', 'SpinAt_m', 'WarningMargin_m'});
end
