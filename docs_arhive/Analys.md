
  1.                                                                     

                                       `apps/reference/domains/decision_making/decision_making.py`:

    1 # ...
    2 notional_cap = decimal.Decimal(str(risk_params.get("cvar_limit_usd", 1000.0)))
    3 # ...
    4 tca_prefs = self.config.get('tca_prefs', {})
    5 risk_budgets = self.config.get('risk_budgets', {})
    6 payoff_ratio_r = decimal.Decimal(str(self.config.get('decision', {}).get('payoff_ratio_r', '2.0')))
    7 
    8 trade_intent_payload = {
    9     # ...
   10     "payoff_ratio_r": float(payoff_ratio_r),
   11     "tca_budget": {
   12         "max_slippage_bps": tca_prefs.get('max_slippage_bps', 50.0),
   13         # ...
   14     },
   15     "risk_budget": {
   16         "trade_cvar95_max_bps": risk_budgets.get('trade_cvar95_max_bps', 100.0),
   17         # ...
   18     },
   19     # ...
   20 }

                                            :

                                                                                                                             (trade_intent_payload)                                            
  FSM-                         EVT:TRADE_INTENT_PROPOSED.                                       ,                                                                                        
            .

   * `payoff_ratio_r` (                                       /                ):                                                                                                                    
               .
   * `tca_budget` (                                                         ):                 ,                                                                                          .               
                                                       (max_slippage_bps),                                         (max_latency_ms)         .
   * `risk_budget` (                         ):                                                                                              (        ., trade_cvar95_max_bps).
   * `notional_cap` (                                        ):                                                           ,                                                                    .

  2.                                                            

                                                                        ,                                  .                                                           :

   1. `decision_making` (                ):              trade_intent_payload                                                                .
   2. FSM Core (        ):                           EVT:TRADE_INTENT_PROPOSED                                                           .
   3. `execution_position` (                ,                                ):                                                           .                              :
       *                    tca_budget                                                                                  (                  ,                  maker-                                    
         taker-          ).
       *                                                  (size)                                 risk_budget.
       *                                                 ,                             max_slippage_bps.
       *                                                               ,        max_latency_ms,                              .

                                          :                                                                                       ,                                   ,                    ,              
                .                                                                                         decision_making                                       ,                 
  execution_position                                                   ,                                            .

  3.                                                

                                                                           .get(key, default_value),      default_value    "                             ".                
  Constitution_FSM,                                                                                                                                      Fail-Fast (                         ,
                                                  ).

                                   :

   1.                                                :                                                                                                                            .yaml         .
   2.                                          :                                                                                   .                                 ,      config_loader.py
                                                                 .                                         .yaml           ,                                                                                   
                       KeyError,                                                                                   .

           1:                                             YAML           

                                      ,      config_loader.py                                                      : trading.yaml      system.yaml.
   * system.yaml                                                                       (        .,                                            ,                                             ).
   * trading.yaml                                                   ,                                                                                   .

                  :                                (payoff_ratio_r, tca_prefs, risk_budgets)                                                    ,                                    
  `config/aurora/trading.yaml`.

           2:                        `config/aurora/trading.yaml`

                                                                               ,                                   :

    1 # ...                                  
    2 
    3 decision:
    4   payoff_ratio_r: 2.0
    5   position_sizing:
    6     kelly_conservative_factor: 0.1
    7     min_position_size_usd: 10.0
    8     max_position_size_usd: 1000.0
    9     #                                   notional_cap         
   10     default_notional_cap_usd: 1000.0
   11 
   12 tca_prefs:
   13   max_slippage_bps: 50.0
   14   max_latency_ms: 5000
   15   maker_preference: "allow"
   16 
   17 risk_budgets:
   18   trade_cvar95_max_bps: 100.0
   19   session_cvar95_max_bps: 200.0
   20
   21 # ...                            

           3:                                 `decision_making.py`

                                                                     ,                                           "Fail-Fast":

    1 # === TRADE INTENT CONSTRUCTION PHASE ===
    2 
    3 try:
    4     #                                                               .                         ,          KeyError -                                           .
    5     decision_config = self.config['decision']
    6     tca_prefs = self.config['tca_prefs']
    7     risk_budgets = self.config['risk_budgets']
    8 
    9     #                                      .                         ,          KeyError.
   10     payoff_ratio_r = decimal.Decimal(str(decision_config['payoff_ratio_r']))
   11 
   12     #                              default_notional_cap_usd                  ,          risk_params                     cvar_limit_usd
   13     default_cap = decimal.Decimal(str(decision_config['position_sizing']['default_notional_cap_usd']))
   14     notional_cap = decimal.Decimal(str(risk_params.get("cvar_limit_usd", default_cap)))
   15 
   16
   17     trade_intent_payload = {
   18         "instrument": symbol,
   19         "side": side,
   20         "p": float(p),
   21         "payoff_ratio_r": float(payoff_ratio_r),
   22         "tca_budget": {
   23             "max_slippage_bps": tca_prefs['max_slippage_bps'],
   24             "max_latency_ms": tca_prefs['max_latency_ms'],
   25             "maker_preference": tca_prefs['maker_preference']
   26         },
   27         "risk_budget": {
   28             "trade_cvar95_max_bps": risk_budgets['trade_cvar95_max_bps'],
   29             "session_cvar95_max_bps": risk_budgets['session_cvar95_max_bps']
   30         },
   31         "size": {
   32             "kelly_fraction": float(kelly_fraction),
   33             "notional_cap_usd": float(position_size)
   34         },
   35         "valid_for_ms": 30000, #                                                                           
   36         "why": [
   37             f"Decision based on signal_score={float(signal_score):.3f}",
   38             f"Features: obi={float(obi):.3f}, tfi={float(tfi):.3f}, absorption={float(absorption):.3f}",
   39             f"Risk approved: kelly={float(kelly_fraction):.3f}, trading_allowed={risk_params.get(
      'is_trading_allowed')}",
   40             f"Position sizing: equity=${float(equity):.2f}, kelly_based=${float(kelly_based_size):.2f},
      final=${float(position_size):.2f}"
   41         ],
   42         "dto_version": "1.0.0",
   43         "schema_ref": "https://aurora.scalp/shared/dto/trade_intent.schema.json"
   44     }
   45
   46 except KeyError as e:
   47     self.logger.critical(f"Configuration key missing: {e}. System cannot make decisions. Please check
      trading.yaml. Halting decision.")
   48     self.clear_internal_state()
   49     return #                                      ,                                                 

                                                      :

   1. SSOT                   :                                                     trading.yaml.
   2. Fail-Fast:                                                               trading.yaml,                                                             "                         ",   
                                                     KeyError,                                                   .
   3.                     :                                                                           .
   4.                         :                                                                                                                                 .

>                                                                                                                                                                                                                          
                                                                                                               decision_making.py

                    .                                                                                                 .

                 :
   1.                    `config/aurora/trading.yaml`:                                          decision, tca_prefs, risk_budgets,                                    
                                       .
   2.                        `decision_making.py`:                                                                                                        "Fail-Fast"             ,       
                                                                                                           .
   3.                                                 :                                     ,                                                           ,                                                  ,           
                                 ,                                                                                          .

                                                                                      .
                                                                                                                                  
          ReadFile config\aurora\trading.yaml     
                                                                                                                                  
             trading.yaml                                                      .                                                                                      default_notional_cap_usd
                                                .

           1:                        `config/aurora/trading.yaml`

                         default_notional_cap_usd: 1000.0                   decision.position_sizing.
                                                                                                                                                                                                                                                                                                                                                    
          Edit config\aurora\trading.yaml: config_version: 1.0.0... => config_version: 1.0.0...                         
                                                                                                                      
        101       kelly_conservative_factor: 0.1  # Conservative Kelly fraction multiplier                            
        102       min_position_size_usd: 10.0  # Minimum position size                                                
        103       max_position_size_usd: 1000.0  # Maximum position size per trade                                    
        104 +     default_notional_cap_usd: 1000.0 # Default notional cap if not provided by risk assessment          
        105                                                                                                           
        106   # Market data settings                                                                                  
        107   market_data:                                                                                            
                                                                                                                                                                                                                                                                                                                                                    
                                             .

           2:                        `apps/reference/domains/decision_making/decision_making.py`

                                              ,                                                                                                         ,              ,                            ,                  
                                                                                      try...except                                               ,                                      .     
                                                                                                 Fail-Fast.

                                                 .
                                                                                                                                                                                                                                                                                                                                                    
          Edit ...pps\decision_making\decision_making.py: """... => """...                                              
                                                                                                                      
        ... first 7 lines hidden ...                                                                                  
        192 +     decision_config = self.config['decision']                                                           
        193 +     sizing_config = decision_config['position_sizing']                                                  
        194 +     tca_prefs = self.config['tca_prefs']                                                                
        195 +     risk_budgets = self.config['risk_budgets']                                                          
        196                                                                                                           
        191 -     # Load TCA preferences from config                                                                  
        192 -     tca_prefs = self.config.get('tca_prefs', {})                                                        
        193 -     risk_budgets = self.config.get('risk_budgets', {})                                                  
        194 -     payoff_ratio_r = decimal.Decimal(str(self.config.get('decision', {}).get('payoff_ratio_r',          
            '2.0')))                                                                                                  
        197 +     # Get sizing parameters from config                                                                 
        198 +     kelly_conservative_factor = decimal.Decimal(str(sizing_config['kelly_conservative_factor']))        
        199 +     min_position_size = decimal.Decimal(str(sizing_config['min_position_size_usd']))                    
        200 +     max_position_size = decimal.Decimal(str(sizing_config['max_position_size_usd']))                    
        201 +     default_notional_cap = decimal.Decimal(str(sizing_config['default_notional_cap_usd']))              
        202                                                                                                           
        203 +     # Get other decision parameters                                                                     
        204 +     payoff_ratio_r = decimal.Decimal(str(decision_config['payoff_ratio_r']))                            
        205 +     valid_for_ms = self.config.get('system', {}).get('trade_intent_validity_ms', 30000)                 
        206 +                                                                                                         
        207 +     # Determine notional cap from risk assessment or config fallback                                    
        208 +     notional_cap = decimal.Decimal(str(risk_params.get("cvar_limit_usd", default_notional_cap)))        
        209 +                                                                                                         
        210 +     # Calculate position size                                                                           
        211 +     kelly_based_size = equity * kelly_fraction * kelly_conservative_factor                              
        212 +     position_size = min(max_position_size, max(min_position_size, kelly_based_size, notional_cap))      
        213 +                                                                                                         
        214 +     # Final validation before emitting                                                                  
        215 +     if position_size < min_position_size:                                                               
        216 +         self.logger.warning(f"Calculated position size {position_size} is below minimum                 
            {min_position_size}. Rejecting.")                                                                         
        217 +         self.clear_internal_state()                                                                     
        218 +         return                                                                                          
        219 +                                                                                                         
        220 +     # Construct the trade intent payload                                                                
        221       trade_intent_payload = {                                                                            
        222           "instrument": symbol,                                                                           
        223           "side": side,                                                                                   
        224           "p": float(p),                                                                                  
        225           "payoff_ratio_r": float(payoff_ratio_r),                                                        
        226           "tca_budget": {                                                                                 
        202 -             "max_slippage_bps": tca_prefs.get('max_slippage_bps', 50.0),                                
        203 -             "max_latency_ms": tca_prefs.get('max_latency_ms', 5000),                                    
        204 -             "maker_preference": tca_prefs.get('maker_preference', "allow")                              
                                                                                                                                                                                                                                                                                                                                        
        227 +             "max_slippage_bps": tca_prefs['max_slippage_bps'],                                          
        228 +             "max_latency_ms": tca_prefs['max_latency_ms'],                                              
        229 +             "maker_preference": tca_prefs['maker_preference']                                           
        230           },                                                                                              
        231           "risk_budget": {                                                                                
        207 -             "trade_cvar95_max_bps": risk_budgets.get('trade_cvar95_max_bps', 100.0),                    
        208 -             "session_cvar95_max_bps": risk_budgets.get('session_cvar95_max_bps', 200.0)                 
                                                                                                                                                                                                                                                                                                                                        
        232 +             "trade_cvar95_max_bps": risk_budgets['trade_cvar95_max_bps'],                               
        233 +             "session_cvar95_max_bps": risk_budgets['session_cvar95_max_bps']                            
        234           },                                                                                              
        235           "size": {                                                                                       
        236               "kelly_fraction": float(kelly_fraction),                                                    
        237               "notional_cap_usd": float(position_size)                                                    
        238           },                                                                                              
        214 -         "valid_for_ms": 30000,                                                                          
                                                                                                                                                                                                                                                                                                                                        
        239 +         "valid_for_ms": valid_for_ms,                                                                   
        240           "why": [                                                                                        
        241               f"Decision based on signal_score={float(signal_score):.3f}",                                
        242               f"Features: obi={float(obi):.3f}, tfi={float(tfi):.3f}, absorption={float(absorption):      
              .3f}",                                                                                                  
        247           "schema_ref": "https://aurora.scalp/shared/dto/trade_intent.schema.json"                        
        248       }                                                                                                   
        249                                                                                                           
        225 -     # Final validation                                                                                  
        226 -     if not self._validate_trade_intent(trade_intent_payload):                                           
        227 -         self.logger.error("Trade intent rejected: final validation failed")                             
                                                                                                                                                                                                                                                                                                                                        
        250 + except KeyError as e:                                                                                   
        251 +     self.logger.critical(f"Configuration key missing: {e}. System cannot make decisions. Please         
            check trading.yaml. Halting decision.")                                                                   
        252       self.clear_internal_state()                                                                         
        229 -         return                                                                                          
                                                                                                                                                                                                                                                                                                                                        
        253 +     return  # Stop execution if config is incomplete                                                    
        254                                                                                                           
        255   # Emit the trade intent                                                                                 
        232 -     self.logger.info(f"Trade intent approved: {symbol} {side} p={float(p):.3f} size=${float             
            (position_size):.2f}")                                                                                    
                                                                                                                                                                                                                                                                                                                                        
        256 + self.logger.info(f"Trade intent approved: {symbol} {side} p={p:.3f} size=${position_size:.2f}")         
        257       self.fsm.emit(                                                                                      
        258           "EVT:TRADE_INTENT_PROPOSED",                                                                    
        259           payload=trade_intent_payload,                                                                   
                                                                                                                                                                                                                                                                                                                                                    
                           decision_making.py                         trading.yaml                   .                                                         Fail-Fast   
                                                                            ,                  "                         ".

                             :                                                            

                                                                                                                    ,                 ,                                      ,                                         
                                             ModuleNotFoundError.

          ,                                                                                                              .                                                                                        ,     
                         ,                                                                                                  execution_position.

                                             : tests/test_acl_message_contracts.py.
                                                                                                                                                                                                                                                                                                                                                                         
          Edit tests\test_acl_message_contracts.py: """Tests for execution_positio... => """Tests for execution_positio...     
                                                                                                                             
         7   # Add vfoundation to path                                                                                       
         8   sys.path.insert(0, str(Path(__file__).parent.parent / "vfoundation"))                                           
         9                                                                                                                   
        10 - from apps.reference.domains.execution_position.contracts import (                                               
        10 + from vfoundation.apps.reference.domains.execution_position.contracts import (                                   
        11       OrderPayload,                                                                                               
        12       PositionPayload,                                                                                            
        13       Side,                                                                                                       
                                                                                                                                                                                                                                                                                                                                                                         
                                              .                                                    9                                                         ModuleNotFoundError                     ,       
                                   .

                                                     test_ci_smoke.py,                                                       ,                                                           .
                                                                                                                                                                                                                                                                                                                                                    
          Edit ...tests\\test_debug_drift_integration.py: """... => """...                                              
                                                                                                                      
        11   sys.path.insert(0, str(Path(__file__).parent.parent / "vfoundation"))                                    
        12                                                                                                            
        13   from vfoundation.obs.debug_api import debug_rid, add_drift_report, _drift_reports, _drift_lock           
        14 - from apps.reference.domains.execution_position.drift_monitor import (                                    
        14 + from vfoundation.apps.reference.domains.execution_position.drift_monitor import (                        
        15       DriftReport, ConfusionMatrix, Mismatch                                                               
        16   )                                                                                                        
        17   from vfoundation.dr import wal                                                                           
                                                                                                                                                                                                                                                                                                                                                    
                                             .                  8                                                   execution_position                                                                    .   
                                                                                           .
                                                                                                                                                                                                                                                                                                                                                       
     -  Edit tests\test_drift_roundtrip.py: from apps.reference.domains.ex... => from vfoundation.apps.referenc...     
                                                                                                                       
        11   sys.path.insert(0, str(Path(__file__).parent.parent / "vfoundation"))                                     
        12                                                                                                             
        13   from vfoundation.core.protocol import Message                                                             
        14 - from apps.reference.domains.execution_position.drift_monitor import compute_drift                         
        14 + from vfoundation.apps.reference.domains.execution_position.drift_monitor import compute_drift             
        15   from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM                                
        16   from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM                            
        17   from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM                              
                                                                                                                                                                                                                                                                                                                                                       

>                                                   decision_making.py                                                                                                

                                      .                                                                                 .                                                                                             
  try...except         ,                                                             .

            ,                                           .                                    decision_making.py,                                                  -                                .

                                 :
   1.                                     ,                                          decision_making.py.
   2.                                                                            _try_make_decision                                                                 .
   3.                                                                                      .

                                                                                             .
                                                                                                                                                                               
          ReadFile ...pps\decision_making\decision_making.py     
                                                                                                                                                                               
                               .                                                                                                                      .                                                
  _try_make_decision,                                             ,                                                                                         "Fail-Fast"                   ,     
                               .

                                 :
   1.                                                   :                                          ,                                                _try_make_decision,                      
                                   ,                                                                                                            .
   2.                                                                :                                                                   _try_make_decision              ,                 
                          .

                             .
                                                                                                                                                                                                                                                                                                                                                    
          Edit ...pps\decision_making\decision_making.py: """... => """...                                              
                                                                                                                      
        ... first 258 lines hidden ...                                                                                
        182 +             "valid_for_ms": int(valid_for_ms),                                                          
        183               "why": [                                                                                    
        184                   f"Decision based on signal_score={float(signal_score):.3f}",                            
        185                   f"Features: obi={float(obi):.3f}, tfi={float(tfi):.3f}, absorption={float               
              (absorption):.3f}",                                                                                     
                                                                                                                                                                                                                                                                                                                                        
        243 -                 f"Risk approved: kelly={float(kelly_fraction):.3f}, trading_allowed=                    
            {risk_params.get('is_trading_allowed')}",                                                                 
        186 +                 f"Risk approved: kelly={float(kelly_fraction):.3f}, trading_allowed=True",              
        187                   f"Position sizing: equity=${float(equity):.2f}, kelly_based=${float                     
              (kelly_based_size):.2f}, final=${float(position_size):.2f}"                                             
        188               ],                                                                                          
        189               "dto_version": "1.0.0",                                                                     
        190               "schema_ref": "https://aurora.scalp/shared/dto/trade_intent.schema.json"                    
        191           }                                                                                               
        192                                                                                                           
                                                                                                                                                                                                                                                                                                                                        
        250 -     except KeyError as e:                                                                               
        251 -         self.logger.critical(f"Configuration key missing: {e}. System cannot make decisions. Please     
            check trading.yaml. Halting decision.")                                                                   
        252 -         self.clear_internal_state()                                                                     
        253 -         return  # Stop execution if config is incomplete                                                
        254 -                                                                                                         
        255 -     # Emit the trade intent                                                                             
        193 +         # 6. === EMIT EVENT ===                                                                         
        194           self.logger.info(f"Trade intent approved: {symbol} {side} p={p:.3f} size=${position_size:.2     
              f}")                                                                                                    
        195           self.fsm.emit(                                                                                  
        196               "EVT:TRADE_INTENT_PROPOSED",                                                                
        198               why="Aggregated decision based on features, risk assessment, and portfolio state."          
        199           )                                                                                               
        200                                                                                                           
                                                                                                                                                                                                                                                                                                                                        
        263 -         # Clear internal state to wait for new data cycle                                               
        264 -         self.clear_internal_state()                                                                     
        265 -                                                                                                         
        201 +     except KeyError as e:                                                                               
        202 +         self.logger.critical(f"Configuration key missing: {e}. System cannot make decisions. Please     
            check trading.yaml. Halting decision.")                                                                   
        203       except Exception as e:                                                                              
        204           self.logger.error(f"Unexpected error in decision making: {e}", exc_info=True)                   
        205 +     finally:                                                                                            
        206 +         # Always clear state after a decision attempt (success or fail) to await a new full set of      
            data                                                                                                      
        207           self.clear_internal_state()                                                                     
                                                                                                                                                                                                                                                                                                                                        
        269 -                                                                                                         
        270 - def _validate_trade_intent(self, trade_intent: dict) -> bool:                                           
        271 -     """                                                                                                 
        272 -     Final validation of trade intent before emission.                                                   
        273 -                                                                                                         
        274 -     Args:                                                                                               
        275 -         trade_intent: Trade intent payload to validate                                                  
        276 -                                                                                                         
        277 -     Returns:                                                                                            
        278 -         True if valid, False otherwise                                                                  
        279 -     """                                                                                                 
        280 -     try:                                                                                                
        281 -         # Validate required fields                                                                      
        282 -         required_fields = ["instrument", "side", "p", "payoff_ratio_r", "size", "tca_budget",           
            "risk_budget"]                                                                                            
        283 -         for field in required_fields:                                                                   
        284 -             if field not in trade_intent:                                                               
        285 -                 self.logger.error(f"Missing required field: {field}")                                   
        286 -                 return False                                                                            
        287 -                                                                                                         
        288 -         # Validate probability                                                                          
        289 -         p = trade_intent.get("p", 0)                                                                    
        290 -         if not (0 < p <= 1):                                                                            
        291 -             self.logger.error(f"Invalid probability: {p}")                                              
        292 -             return False                                                                                
        293 -                                                                                                         
        294 -         # Validate position size                                                                        
        295 -         size = trade_intent.get("size", {})                                                             
        296 -         notional_cap = size.get("notional_cap_usd", 0)                                                  
        297 -         if notional_cap <= 0:                                                                           
        298 -             self.logger.error(f"Invalid position size: {notional_cap}")                                 
        299 -             return False                                                                                
        300 -                                                                                                         
        301 -         return True                                                                                     
        302 -                                                                                                         
        303 -     except Exception as e:                                                                              
        304 -         self.logger.error(f"Error validating trade intent: {e}")                                        
        305 -         return False                                                                                    
        306 -                                                                                                         
        307 - def clear_internal_state(self) -> None:                                                                 
        308 -     """Clear internal data storage to prepare for next decision cycle."""                               
        309 -     self.latest_features = None                                                                         
        310 -     self.latest_risk = None                                                                             
        311 -     self.latest_portfolio = None                                                                        
                                                                                                                                                                                                                                                                                                                                                    
                                                                                decision_making.py                   .

                                                                                                                                                                            .                                           
                 ModuleNotFoundError                                                           ,                                                                                       .

                                               test_drift_roundtrip.py                 8                                  .
                                                                                                                                                                                                                                                                                                                                                    
          Edit tests\test_drift_roundtrip.py: """... => """...                                                          
                                                                                                                      
        11   sys.path.insert(0, str(Path(__file__).parent.parent / "vfoundation"))                                    
        12                                                                                                            
        13   from vfoundation.core.protocol import Message                                                            
        14 - from apps.reference.domains.execution_position.drift_monitor import compute_drift                        
        14 + from vfoundation.apps.reference.domains.execution_position.drift_monitor import compute_drift            
        15   from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM                               
        16   from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM                           
        17   from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM                             
                                                                                                                                                                                                                                                                                                                                                    
                      .                                           .
                                                                                                                                                                                                                                                                                                                                                    
          Edit tests\test_drift_unit.py: """... => """...                                                               
                                                                                                                      
         9   # Add vfoundation to path                                                                                
        10   sys.path.insert(0, str(Path(__file__).parent.parent / "vfoundation"))                                    
        11                                                                                                            
        12 - from apps.reference.domains.execution_position.drift_monitor import (                                    
        12 + from vfoundation.apps.reference.domains.execution_position.drift_monitor import (                        
        13       compute_drift,                                                                                       
        14       aggregate_drift_metrics,                                                                             
        15       ConfusionMatrix,                                                                                     
                                                                                                                                                                                                                                                                                                                                                    
                      .                                                              .
                                                                                                                                                                                                                                                                                                                                                    
          Edit \test_execpos_contracts_pydantic_v2.py: """... => """...                                                 
                                                                                                                      
        11   # Add vfoundation to path                                                                                
        12   sys.path.insert(0, str(Path(__file__).parent.parent / "vfoundation"))                                    
        13                                                                                                            
        14 - from apps.reference.domains.execution_position.contracts import (                                        
        14 + from vfoundation.apps.reference.domains.execution_position.contracts import (                            
        15       OrderPayload,                                                                                        
        16       PositionPayload,                                                                                     
        17       Side,                                                                                                
                                                                                                                                                                                                                                                                                                                                                    
                      .                                                              .
                                                                                                                                                                                                                                                                                                                                                    
          Edit tests\test_fsm_close.py: """... => """...                                                                
                                                                                                                      
         6   import time                                                                                              
         7                                                                                                            
         8   from vfoundation.core.protocol import Message                                                            
         9 - from apps.reference.domains.execution_position.fsm_close import (                                        
         9 + from vfoundation.apps.reference.domains.execution_position.fsm_close import (                            
        10       CloseFlowFSM,                                                                                        
        11 -     CloseState,                                                                                          
        11 +     State,                                                                                               
        12   )                                                                                                        
        13                                                                                                            
        14                                                                                                            
                                                                                                                                                                                                                                                                                                                                                    
                      .                                                              .
                                                                                                                                                                                                                                                                                                                                                    
          Edit tests\test_fsm_manage.py: """... => ...                                                                  
                                                                                                                      
         1 +                                                                                                          
         2   """                                                                                                      
         3   Unit tests for Manage Flow FSM (FSMP-P1-T02).                                                            
         4                                                                                                            
         4 - Coverage: PARTIAL_FILL/FILL     TRACKING, UPD     DEC:ADJUST (trail/BE/time).                                
         5 + Coverage: trail_pct, EVT:FILL, UPD:PRICE, DEC:ADJUST.                                                    
         6   """                                                                                                      
         6 - import time                                                                                              
         7 + import sys                                                                                               
         8 + from pathlib import Path                                                                                 
         9                                                                                                            
        10 + # Add vfoundation to path                                                                                
        11 + sys.path.insert(0, str(Path(__file__).parent.parent / "vfoundation"))                                    
        12 +                                                                                                          
        13   from vfoundation.core.protocol import Message                                                            
         9 - from apps.reference.domains.execution_position.fsm_manage import (                                       
        14 + from vfoundation.apps.reference.domains.execution_position.fsm_manage import (                           
        15       ManageFlowFSM,                                                                                       
        11 -     ManageState,                                                                                         
        16 +     State,                                                                                               
        17   )                                                                                                        
        18                                                                                                            
        19                                                                                                            
                                                                                                                                                                                                                                                                                                                                                    
                      .                                                              .
                                                                                                                                                                                                                                                                                                                                                    
          Edit tests\test_fsm_open.py: """... => """...                                                                 
                                                                                                                      
         6   from decimal import Decimal                                                                              
         7                                                                                                            
         8   from vfoundation.core.protocol import Message                                                            
         9 - from apps.reference.domains.execution_position.fsm_open import (                                         
         9 + from vfoundation.apps.reference.domains.execution_position.fsm_open import (                             
        10       OpenFlowFSM,                                                                                         
        11 -     OpenState,                                                                                           
        11 +     State,                                                                                               
        12   )                                                                                                        
        13                                                                                                            
        14                                                                                                            
                                                                                                                                                                                                                                                                                                                                                    
                      .                                                              .
                                                                                                                                                                                                                                                                                                                                                    
          Edit tests\test_fsm_shadow_roundtrip.py: """... => """...                                                     
                                                                                                                      
        ... first 259 lines hidden ...                                                                                
        168 -         op="EVT",                                                                                       
        169 -         verb="REJECTED",                                                                                
        170 -         src="exchange_stub",                                                                            
        171 -         dst="execution_position",                                                                       
        172 -         rid="test-e2e-003",                                                                             
        173 -         why="order rejected",                                                                           
        174 -     )                                                                                                   
        111                                                                                                           
                                                                                                                                                                                                                                                                                                                                        
        176 -     dec_close = exec_fsm.on_error_events(evt_reject)                                                    
        112 + def test_replay_empty_wal(temp_wal_dir):                                                                
        113 +     """Test replay on an empty WAL directory does not call handler."""                                  
        114 +     wal.set_wal_dir(temp_wal_dir)                                                                       
        115                                                                                                           
                                                                                                                                                                                                                                                                                                                                        
        178 -     assert dec_close is not None                                                                        
        179 -     assert dec_close.op == "DEC"                                                                        
        180 -     assert dec_close.verb == "CLOSE"                                                                    
        181 -     assert dec_close.why == "CLOSE_EMERGENCY"                                                           
        182 -     assert dec_close.pld["reduce_only"] is True                                                         
        116 +     replay_handler = MagicMock()                                                                        
        117                                                                                                           
                                                                                                                                                                                                                                                                                                                                        
        184 -     # Verify WAL                                                                                        
        185 -     wal_entries = wal.read_all()                                                                        
        186 -     close_entry = next((e for e in wal_entries if e.get("op") == "DEC" and e.get("verb") == "CLOSE"     
            ), None)                                                                                                  
        187 -     assert close_entry is not None                                                                      
        118 +     replay.replay_from_wal(replay_handler)                                                              
        119                                                                                                           
                                                                                                                                                                                                                                                                                                                                        
        189 -                                                                                                         
        190 - def test_shadow_idempotency(setup_shadow_env):                                                          
        191 -     """                                                                                                 
        192 -     Test idempotency: 50 parallel CMD:OPEN with same key     1 DEC.                                       
        193 -     """                                                                                                 
        194 -     router, acl = setup_shadow_env                                                                      
        195 -                                                                                                         
        196 -     cmd = Message(                                                                                      
        197 -         op="CMD",                                                                                       
        198 -         verb="OPEN",                                                                                    
        199 -         src="test",                                                                                     
        200 -         dst="execution_position",                                                                       
        201 -         rid="test-idem-001",                                                                            
        202 -         why="idempotency test",                                                                         
        203 -         idempotent_key="same-key-123",                                                                  
        204 -         pld={                                                                                           
        205 -             "symbol": "ADAUSDT",                                                                        
        206 -             "side": "BUY",                                                                              
        207 -             "qty": "100.0",                                                                             
        208 -         },                                                                                              
        209 -     )                                                                                                   
        210 -                                                                                                         
        211 -     results = []                                                                                        
        212 -     for i in range(50):                                                                                 
        213 -         result = exec_fsm.on_cmd_open(cmd)                                                              
        214 -         if result and result.op == "DEC":                                                               
        215 -             results.append(result)                                                                      
        216 -                                                                                                         
        217 -     # Should have only 1 DEC (others dedup or inflight)                                                 
        218 -     assert len(results) <= 1  # Idempotency enforced                                                    
        219 -                                                                                                         
        220 -                                                                                                         
        221 - def test_shadow_metrics_export(setup_shadow_env):                                                       
        222 -     """                                                                                                 
        223 -     Test metrics export: fsm_decision_ms_p95, *_total counters.                                         
        224 -     """                                                                                                 
        225 -     router, acl = setup_shadow_env                                                                      
        226 -                                                                                                         
        227 -     # Generate activity                                                                                 
        228 -     for i in range(10):                                                                                 
        229 -         cmd = Message(                                                                                  
        230 -             op="CMD", verb="OPEN", src="t", dst="ep", rid=f"r{i}", why="m",                             
        231 -             idempotent_key=f"k{i}",                                                                     
        232 -             pld={"symbol": "BTC", "side": "BUY", "qty": "1.0"}                                          
        233 -         )                                                                                               
        234 -         exec_fsm.on_cmd_open(cmd)                                                                       
        235 -                                                                                                         
        236 -     metrics = exec_fsm.get_metrics()                                                                    
        237 -                                                                                                         
        238 -     assert "fsm_decision_ms_p95" in metrics                                                             
        239 -     assert "fsm_open_decisions_total" in metrics                                                        
        240 -     assert "fsm_adjust_decisions_total" in metrics                                                      
        241 -     assert "fsm_close_decisions_total" in metrics                                                       
        242 -     assert "fsm_guard_rejects_total" in metrics                                                         
        243 -     assert "fsm_errors_total" in metrics                                                                
        244 -                                                                                                         
        245 -     assert metrics["fsm_decision_ms_p95"] >= 0                                                          
        246 -     assert metrics["fsm_open_decisions_total"] >= 1                                                     
        120 +     replay_handler.assert_not_called()                                                                  
                                                                                                                                                                                                                                                                                                                                                    
                      .                                             ,                              execution_position.
                                                                                                                                                                                                                                                                                                                                                    
          Edit ...sts\\test_metrics_drift_integration.py: """... => """...                                              
                                                                                                                      
         9   sys.path.insert(0, str(Path(__file__).parent.parent / "vfoundation"))                                    
        10                                                                                                            
        11   from vfoundation.obs.debug_api import metrics, add_drift_report, _drift_reports, _drift_lock             
        12 - from apps.reference.domains.execution_position.drift_monitor import (                                    
        13 -     DriftReport, ConfusionMatrix                                                                         
        12 + from vfoundation.apps.reference.domains.execution_position.drift_monitor import (                        
        13 +     compute_drift,                                                                                       
        14 +     aggregate_drift_metrics,                                                                             
        15   )                                                                                                        
        16                                                                                                            
        17                                                                                                            
                                                                                                                                                                                                                                                                                                                                                    
                                             ,       '              execution_position.

                                              , tests/test_ci_smoke.py,                                              .                                        ,                           
                                                                          .
                                                                                                                                                                                                                                                                                                                                                    
          Edit tests\test_ci_smoke.py: """... => """...                                                                 
                                                                                                                      
        12   import sys                                                                                               
        13   from pathlib import Path                                                                                 
        14   from fastapi.testclient import TestClient                                                                
        15 - from apps.reference.api.main import app                                                                  
        15 + from vfoundation.apps.reference.api.main import app                                                      
        16   from vfoundation.config import config                                                                    
        17                                                                                                            
        18   @pytest.fixture(autouse=True)                                                                            
                                                                                                                                                                                                                                                                                                                                                    
                                                                                              .

            ,                                                                 ,                                                  ,                                                                                  ,
                                                                                                                             .                                                                                     ,
                                decision_making.py.

                   pytest.
                                                                                                                                                                                                                                                                                                                                                    
          Shell pytest -q --cov=vfoundation --cov=apps                                                                  
                                                                                                                      
        ... first 281 lines hidden ...                                                                                
                                                                                                                      
        E                                                                      ^                                      
                                                                                                                      
        E   SyntaxError: unterminated triple-quoted string literal (detected at line 121)                             
                                                                                                                      
        __________________________ ERROR collecting tests/test_metrics_drift_integration.py                           
        __________________________                                                                                    
        ImportError while importing test module                                                                       
        'C:\Users\job11\Music\Olimp_v1\tests\test_metrics_drift_integration.py'                                       
        .                                                                                                             
                                                                                                                      
        Hint: make sure your test modules/packages have valid Python names.                                           
                                                                                                                      
        Traceback:                                                                                                    
                                                                                                                      
        C:\Program                                                                                                    
        Files\WindowsApps\PythonSoftwareFoundation.Python.3.11_3.11.2544.0_x64__qbz5n2kfra8p0\Lib\importlib\          
        __init__.py:126: in import_module                                                                             
                                                                                                                      
            return _bootstrap._gcd_import(name[level:], package, level)                                               
                                                                                                                      
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^                                               
                                                                                                                      
        tests\test_metrics_drift_integration.py:12: in <module>                                                       
                                                                                                                      
            from vfoundation.apps.reference.domains.execution_position.drift_monitor import (                         
                                                                                                                      
        E   ModuleNotFoundError: No module named                                                                      
        'vfoundation.apps.reference.domains.execution_position.drift_monitor'                                         
        ============================================== warnings summary                                               
        ==============================================                                                                
        vfoundation\vfoundation\config.py:20                                                                          
                                                                                                                      
          C:\Users\job11\Music\Olimp_v1\vfoundation\vfoundation\config.py:20: UserWarning: RBAC_ADMIN_TOKENS not      
        set -                                                                                                         
        using INSECURE dev default 'dev-admin-token'. Set RBAC_ADMIN_TOKENS env var in production!                    
                                                                                                                      
            self.rbac_admin_tokens: List[str] = self._get_admin_tokens()                                              
                                                                                                                      
                                                                                                                      
                                                                                                                      
        vfoundation\vfoundation\config.py:21                                                                          
                                                                                                                      
          C:\Users\job11\Music\Olimp_v1\vfoundation\vfoundation\config.py:21: UserWarning: SIGNING_KEY not set -      
        using                                                                                                         
        INSECURE dev default. Set SIGNING_KEY env var in production!                                                  
                                                                                                                      
            self.signing_key: str = self._get_signing_key()                                                           
                                                                                                                      
                                                                                                                      
                                                                                                                      
        vfoundation\vfoundation\config.py:116                                                                         
                                                                                                                      
          C:\Users\job11\Music\Olimp_v1\vfoundation\vfoundation\config.py:116: UserWarning: WORKER_ID not set -       
        using g                                                                                                       
        enerated ID: Password-baa77cf4. Set WORKER_ID env var for stable identification.                              
                                                                                                                      
            self.worker_id: str = self._get_worker_id()                                                               
                                                                                                                      
                                                                                                                      
                                                                                                                      
        -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html                                       
                                                                                                                      
        ========================================== short test summary info                                            
        ===========================================                                                                   
        ERROR tests/test_acl_message_contracts.py                                                                     
                                                                                                                      
        ERROR tests/test_ci_smoke.py                                                                                  
                                                                                                                      
        ERROR tests/test_debug_drift_integration.py                                                                   
                                                                                                                      
        ERROR tests/test_drift_roundtrip.py                                                                           
                                                                                                                      
        ERROR tests/test_drift_unit.py                                                                                
                                                                                                                      
        ERROR tests/test_execpos_contracts_pydantic_v2.py                                                             
                                                                                                                      
        ERROR tests/test_fsm_close.py                                                                                 
                                                                                                                      
        ERROR tests/test_fsm_manage.py                                                                                
                                                                                                                      
        ERROR tests/test_fsm_open.py                                                                                  
                                                                                                                      
        ERROR tests/test_fsm_shadow_roundtrip.py                                                                      
                                                                                                                      
        ERROR tests/test_metrics_drift_integration.py                                                                 
                                                                                                                      
        !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! Interrupted: 11 errors during collection                                   
        !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!                                                                            
        3 warnings, 11 errors in 23.56s                                                                               
                                                                                                                                                                                                                                                                                                                                                    
                                            ,                                    .                           .

                                        :

  pytest                                                    ,                                         .
   *                          : ModuleNotFoundError: No module named 'apps.reference.domains.execution_position'
   *                        : ModuleNotFoundError: No module named 'vfoundation.apps.reference.domains.execution_position.contracts'

                     ,                                                                                                              ,                                 . Python                                   
                     vfoundation,                                                       .

                :

                                             ,      Python                              .                    __init__.py                                                                                 
              .                 ,                    vfoundation/apps/reference/domains                                                       Python-              ,       
  sys.path                                               ,                                                     .

                                                                                                                                                                                       sys.path                  
                               ,                                                                                .

                            :

   1.                                                       :                                      apps/reference/domains/execution_position.
   2.                                          :                                 vfoundation/apps/reference/domains/execution_position                                
                           apps/reference/domains/execution_position.                                                                                                      
                                     .
   3.                                              :                                                                                                         ,                           ,                           
                              apps.reference.domains.execution_position.
   4.                                               :                                                  pytest,         ,                ,                                                                          
                .

                                                                                                    .                                                            .
