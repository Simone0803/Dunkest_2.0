# Coach Monte Carlo backtest — supersession note

V1 and V2 of `dunkest_coach_score_forecast_monte_carlo_walk_forward` are superseded by V3. They initialized the team-score volatility, score-correlation and overtime priors at the beginning of the first test season rather than warming them up on all games completed before the test period. V3 initializes these priors from all historical NBA games strictly before the first target date, then updates history only after each target date has been fully forecast. Use V3 for conclusions.
