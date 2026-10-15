#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "FDTravelPoint.generated.h"

/**
 * ファストトラベルの行き先 (F キーのメニューに並ぶ)。ミニマップにも点で出る。
 * tools/ue/setup_project.py が道路の上に道路の向きで置く。エディタで手で置き足してもよい。
 * 着いたときの高さは地面に合わせ直すので、Z は地面より上ならどこでもよい。
 */
UCLASS()
class FUKUOKADRIVE_API AFDTravelPoint : public AActor
{
	GENERATED_BODY()

public:
	AFDTravelPoint();

	/** メニューに出す名前 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Travel")
	FString DisplayName;

	/** メニューでの並び順 (小さいほど上) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Travel")
	int32 Order = 0;

#if WITH_EDITORONLY_DATA
	/** エディタで場所と向きがわかるように矢印を出す */
	UPROPERTY()
	TObjectPtr<class UArrowComponent> Arrow;
#endif
};
