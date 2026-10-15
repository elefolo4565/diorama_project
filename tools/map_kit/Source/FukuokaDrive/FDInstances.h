#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "FDInstances.generated.h"

class UInstancedStaticMeshComponent;

/**
 * 同じメッシュをたくさん並べるだけのアクター (木・ガードレール・花)。
 * tools/ue/setup_project.py がメッシュと並べる位置を入れる。景観用なので当たり判定はない。
 * 花と桜は SeasonMask の季節だけ見える (AFDTimeOfDay が Y キーの日付に合わせて ApplySeason を呼ぶ)。
 */
UCLASS()
class FUKUOKADRIVE_API AFDInstances : public AActor
{
	GENERATED_BODY()

public:
	AFDInstances();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Instances")
	TObjectPtr<UInstancedStaticMeshComponent> Instances;

	/** 見える季節のビット (1 = 春 3-5 月、2 = 夏 6-8 月、4 = 秋 9-11 月、8 = 冬 12-2 月)。0 ならいつも見える */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Instances")
	int32 SeasonMask = 0;

	/** エディタのビューポートで見せる季節の月 (プレイの初めの日付 6/21 と同じ夏)。季節の花が重なって見えないように */
	static constexpr int32 EditorPreviewMonth = 6;

	/** 月 (1-12) の季節のビット */
	static int32 SeasonBit(int32 Month);

	/** Month の季節に咲いていなければ隠す (SeasonMask が 0 なら何もしない) */
	void ApplySeason(int32 Month);

	virtual void PostRegisterAllComponents() override;
};
