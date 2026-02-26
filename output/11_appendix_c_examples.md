# Appendix C: Illustrative Examples by Method

*Auto-extracted from the corpus to illustrate how each method 
captures different dimensions of coverage bias.*


## 1. Prosecutor-Attributed Theme Detection (d = 0.43)

This method detects anti-prosecutor narrative themes (recall campaigns, 
soft-on-crime framing, etc.) attributed to specific prosecutors.


### Example 1a: High theme score (Progressive prosecutor)

**Headline**: 'Boudin Blunders': SF DA's downfall leading up to recall
**Date**: 2022-06-08
**Publication**: kron4.com
**Prosecutor**: Chesa Boudin (Progressive)
**Score (ta_composite_score)**: 21.2500
**Details**: crime_rising, soft_on_crime, case_dismissal, recall, public_safety_failure (4 detection methods)

> 'boudin blunders': sf da's downfall leading up to recall san francisco (kron) -- chesa boudin's tenure as san francisco district attorney was marred by battles with the police department and clashes with prosecutors who viewed him as soft on crime. at the polls on tuesday, san franciscans overwhelmingly voted to oust their progressive district attorney. partial returns showed 60% of voters supported recalling boudin. boudin, 41, is a former public defender. he narrowly won office in november 2019 with a platform promising to seek alternatives to incarceration, end the racist war on drugs, and hold police officers accountable. reducing incarceration rates was a personal issue for boudin. his father served four decades behind prison bars for his role in a 1981 robbery in new york. but over the past two years in san francisco, brazen shoplifting, car break-ins, drug dealing, home burglaries, and attacks against asian american residents left blackeyes on boudin's time in office. boudin's critics say his policies embolden criminals to commit crimes without fear of consequences. a heated recall campaign, "yes on h," ensued. brooke jenkins, one of san francisco's top homicide prosecutors, left the district attorney's office and joined the recall campaign. jenkins said she quit [...]

### Example 1b: Recall campaign theme (Progressive)

### Example 1c: Soft-on-crime theme (Progressive)

**Headline**: 'Boudin Blunders': SF DA's downfall leading up to recall
**Date**: 2022-06-08
**Publication**: kron4.com
**Prosecutor**: Chesa Boudin (Progressive)
**Score (ta_composite_score)**: 21.2500
**Details**: crime_rising, soft_on_crime, case_dismissal, recall, public_safety_failure (4 detection methods)

> 'boudin blunders': sf da's downfall leading up to recall san francisco (kron) -- chesa boudin's tenure as san francisco district attorney was marred by battles with the police department and clashes with prosecutors who viewed him as soft on crime. at the polls on tuesday, san franciscans overwhelmingly voted to oust their progressive district attorney. partial returns showed 60% of voters supported recalling boudin. boudin, 41, is a former public defender. he narrowly won office in november 2019 with a platform promising to seek alternatives to incarceration, end the racist war on drugs, and hold police officers accountable. reducing incarceration rates was a personal issue for boudin. his father served four decades behind prison bars for his role in a 1981 robbery in new york. but over the past two years in san francisco, brazen shoplifting, car break-ins, drug dealing, home burglaries, and attacks against asian american residents left blackeyes on boudin's time in office. boudin's critics say his policies embolden criminals to commit crimes without fear of consequences. a heated recall campaign, "yes on h," ensued. brooke jenkins, one of san francisco's top homicide prosecutors, left the district attorney's office and joined the recall campaign. jenkins said she quit [...]

### Example 1d: No themes detected (Traditional prosecutor)

**Headline**: Man accused of hitting woman with car in Millbrae being examined for competency
**Date**: 2021-09-24
**Publication**: San Mateo Daily Journal
**Prosecutor**: Steve Wagstaffe (Traditional)
**Score (ta_composite_score)**: 0.0000
**Details**: No anti-prosecutor themes detected

> man accused of hitting woman with car in millbrae being examined for competency lawyers representing garrett young, a man accused of running over a woman with his car over a dispute at his safeway workplace, do not believe he is competent to stand trial and have asked for doctors to determine his mental competency, the san mateo county district attorney's office said thursday. young, 23, of millbrae, allegedly ran over a homeless woman with his bmw suv several times outside his millbrae safeway workplace sept. 20 because she had yelled at him repeatedly for several months about the state of work areas that were his responsibility. detectives interviewed young following an investigation and determined that he was responsible for striking the victim in front of starbucks, the sheriff's office said. the woman is on life support and in critical condition, prosecutors said. young appeared in court thursday. prosecutors said that a doctor would be appointed monday to determine if he can stand trial, which is expected to take six to eight weeks.


## 2. Keyword Bias Score (Method C, d = -0.22)

Weighted keyword scoring based on crime-related terminology, 
negativity markers, and prosecutor-specific framing.


### Example 2a: Most negative keyword score (Progressive)

**Headline**: Boudin's impact on prosecutions
**Date**: 2021-11-07
**Publication**: San Francisco Chronicle
**Prosecutor**: Chesa Boudin (Progressive)
**Score (score_keywords)**: -0.5556
**Details**: Keyword themes: releasing_criminals, case_dismissal, office_dysfunction, recall, public_safety_failure

> boudin's impact on prosecutions when chesa boudin ran for san francisco district attorney in 2019, he promised to approach crime differently than his predecessors, in part by no longer prosecuting lower-level offenses such as recreational drug use. he also pledged to take more rape cases to trial, even if that meant he would lose those cases more frequently. less than two years after taking office, boudin faces a likely recall election after critics of his administration garnered more than 83,000 signatures from residents who believe he has made the city less safe. to explore that claim, the chronicle conducted a comprehensive review of how often his office decides to prosecute arrested individuals and how often it secures convictions in selected types of crime. boudin's overall charging rate is 48%, slightly lower than predecessor george gascón's 54% in his last two years and on par with gascón's charging rates in 2016 and 2017. but overall charging rates can be misleading because the types of cases the d.a. receives from police can change significantly from year to year, especially during abnormal periods such as the current global pandemic. a review of charging rates for specific crime types, which allows a more accurate [...]

### Example 2b: Crime-rising theme (Progressive)

**Headline**: Inside the Tenderloin, can a city fix a neighborhood while staying true to its values?
**Date**: 2022-02-24
**Publication**: sfgate.com
**Prosecutor**: Chesa Boudin (Progressive)
**Score (score_keywords)**: -0.4444
**Details**: Keyword themes: crime_rising, soft_on_crime, releasing_criminals, recall

> inside the tenderloin, can a city fix a neighborhood while staying true to its values? she is a reflection of where she lives, of its unpredictable rhythms, of its churn and tenacity. her peak-and-valley journey has taken her from homelessness to a rent-controlled apartment, from pride over her daughter's academic brilliance to the pain in knowing she would need to send her away for school, from out-of-work lyft driver to unpaid advocate pushing for the tenderloin's children to be shown the wild beauty beyond these streets. it is a story bound and shaped by the tenderloin, historically a first stop for the hopeful and a last for the desperate. for bryant it is simply home, another of its 36,000 residents seeking opportunity and security within its downtown boundaries, angry they have earned through hard experience the unusual urban ability to tell the difference between human waste and dog feces by smell alone. "unless you are living in the tl you don't know it, you can't be committed to it," said bryant, who is black, taking in the winter sun beaming between buildings one recent morning. the neighborhood, many things to many people over the decades, helps define the sharpest edge [...]


## 4. Cross-Method Comparison

The same article scored by multiple methods, illustrating how 
different methods capture different dimensions.


### Example 4a: Multi-method negative (Progressive)

**Headline**: How Boudin is prosecuting cases
**Date**: 2021-11-07
**Publication**: San Francisco Chronicle
**Prosecutor**: Chesa Boudin (Progressive)
**Score (composite_bias_score)**: -0.5556
**Details**: All scores: score_keywords=-0.556, ta_composite_score=13.120

> how boudin is prosecuting cases when chesa boudin ran for san francisco district attorney in 2019, he promised to approach crime differently than his predecessors, in part by no longer prosecuting lower-level offenses such as recreational drug use. he also pledged to take more rape cases to trial, even if that meant he would lose those cases more frequently. less than two years after taking office, boudin faces a likely recall election after critics of his administration garnered more than 83,000 signatures from residents who believe he has made the city less safe. to explore that claim, the chronicle conducted a comprehensive review of how often his office decides to prosecute arrested individuals and how often it secures convictions in selected types of crime. boudin's overall charging rate is 48%, slightly lower than predecessor george gascón's 54% in his last two years and on par with gascón's charging rates in 2016 and 2017. but overall charging rates can be misleading because the types of cases the d.a. receives from police can change significantly from year to year, especially during abnormal periods such as the current global pandemic. a review of charging rates for specific crime types, which allows a more [...]

### Example 4b: Multi-method neutral (Traditional)

**Headline**: Former Ohio college physician faces multiple rape charges
**Date**: 2022-10-25
**Publication**: sfgate.com
**Prosecutor**: Brooke Jenkins (Traditional)
**Score (composite_bias_score)**: 0.0000
**Details**: All scores: score_keywords=0.000, ta_composite_score=0.000

> former ohio college physician faces multiple rape charges donald gronbeck, 42, was indicted thursday in greene county on 50 felony and misdemeanor charges that include nine counts of rape. he served as the campus physician at antioch from 2015 through 2019 and maintained a medical practice in yellow springs where the small liberal arts school is located. gronbeck surrendered his medical license earlier this year after the state medical board of ohio suspended him in late january based on complaints made by eight female patients. he has been held in the greene county jail since his arrest friday. he is scheduled to be arraigned on thursday. "there is definitely another version of the events as told by the prosecutor's office," gronbeck's attorney, john paul rion, said. a greene county sheriff's detective at a news briefing monday said the investigation of gronbeck was spurred by complaints from patients. ohio attorney general dave yost at the news briefing called the allegations against gronbeck "an incredibly graphic and brutal betrayal of trust." he said one of the victims recorded a portion of the acts committed by gronbeck. antioch college president jane fernandes in a statement released when gronbeck's medical license was suspended in [...]
