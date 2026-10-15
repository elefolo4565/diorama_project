#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "FDGameMode.generated.h"

/** プレイ開始時に PlayerStart にクロスカブを出す (エディタの再生でもカメラの位置ではなく PlayerStart から)。時刻の切り替え (FDTimeOfDay) と Tab のメニュー (FDGameMenu) がレベルに無ければ置く */
UCLASS()
class FUKUOKADRIVE_API AFDGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AFDGameMode();

	virtual void StartPlay() override;
	virtual AActor* ChoosePlayerStart_Implementation(AController* Player) override;
};
